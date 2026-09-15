"""Bench commands for the Config Pack lifecycle.

The commands intentionally orchestrate the same service layer as the Desk pages;
they do not implement an alternate archive, comparison, or deployment format.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click
import frappe
from frappe.commands import get_site, pass_context

from frappe_config_pack.api.deployment import _SavepointGuard
from frappe_config_pack.api.import_pack import _target_environment
from frappe_config_pack.core.exceptions import ConfigPackError
from frappe_config_pack.services.config_pack_builder import ConfigPackBuildService
from frappe_config_pack.services.dependency_engine import DependencyEngine, FrappeDependencyTarget
from frappe_config_pack.services.deployment import DeploymentService, FrappeResourceExecutor
from frappe_config_pack.services.diff_engine import DiffEngine
from frappe_config_pack.services.drift import DriftService
from frappe_config_pack.services.installations import FrappeInstallationRepository
from frappe_config_pack.services.preflight import PackagePreflightService, PreflightStatus
from frappe_config_pack.services.reader import PackageReader
from frappe_config_pack.services.snapshot import FrappeRollbackExecutor, RollbackService, SnapshotService
from frappe_config_pack.services.target_reader import FrappeTargetReader


@click.group("config-pack")
def config_pack() -> None:
	"""Build, review, deploy, audit, and roll back Config Packs."""


@config_pack.command("list")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def list_packs(context: Any, as_json: bool) -> None:
	"""List Config Pack records available on the selected site."""

	with _site_session(context):
		rows = frappe.get_all(
			"Config Pack",
			fields=["name", "package_name", "slug", "version", "status", "package_checksum", "last_built_on"],
			order_by="modified desc",
		)
		_emit({"items": rows, "count": len(rows)}, as_json)


@config_pack.command("build")
@click.argument("config_pack")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def build(context: Any, config_pack: str, as_json: bool) -> None:
	"""Build and privately store an archive for CONFIG_PACK."""

	with _site_session(context):
		pack = frappe.get_doc("Config Pack", config_pack)
		pack.check_permission("write")
		result = ConfigPackBuildService().build_and_store(pack)
		frappe.db.commit()
		_emit({"config_pack": pack.name, **result}, as_json)


@config_pack.command("export")
@click.argument("config_pack")
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False, writable=True), required=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def export(context: Any, config_pack: str, output: Path, as_json: bool) -> None:
	"""Copy a built CONFIG_PACK archive to OUTPUT."""

	with _site_session(context):
		pack = frappe.get_doc("Config Pack", config_pack)
		pack.check_permission("read")
		if not pack.package_file:
			raise click.ClickException("Build this Config Pack before exporting it.")
		content = frappe.get_doc("File", pack.package_file).get_content()
		output.parent.mkdir(parents=True, exist_ok=True)
		output.write_bytes(content)
		_emit({"config_pack": pack.name, "output": str(output), "bytes": len(content)}, as_json)


@config_pack.command("inspect")
@click.argument("package", type=click.Path(exists=True, path_type=Path, dir_okay=False, readable=True))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def inspect(context: Any, package: Path, as_json: bool) -> None:
	"""Validate PACKAGE and report compatibility without target mutation."""

	with _site_session(context):
		result = _preflight(package.read_bytes())
		_emit(result.as_dict(), as_json)
		if result.status is PreflightStatus.INCOMPATIBLE:
			raise click.ClickException("Package is incompatible with this site.")


@config_pack.command("diff")
@click.argument("package", type=click.Path(exists=True, path_type=Path, dir_okay=False, readable=True))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def diff(context: Any, package: Path, as_json: bool) -> None:
	"""Compare PACKAGE with the selected site without changing it."""

	with _site_session(context):
		archive = package.read_bytes()
		preflight = _preflight(archive)
		response: dict[str, Any] = {"preflight": preflight.as_dict(), "diff": None}
		if preflight.status is not PreflightStatus.INCOMPATIBLE:
			parsed = PackageReader().read(archive)
			dependencies = DependencyEngine()
			target = FrappeDependencyTarget()
			response["diff"] = DiffEngine().compare(
				parsed.resources,
				FrappeTargetReader(),
				dependency_checker=lambda payload: dependencies.missing_for_payload(payload, parsed.resources, target),
			).as_dict()
		_emit(response, as_json)
		if preflight.status is PreflightStatus.INCOMPATIBLE:
			raise click.ClickException("Package is incompatible with this site.")


@config_pack.command("apply")
@click.argument("package", type=click.Path(exists=True, path_type=Path, dir_okay=False, readable=True))
@click.option("--dry-run", is_flag=True, help="Show the deployment plan without changing the target.")
@click.option("--selection", multiple=True, metavar="KEY=ACTION", help="Reviewed action for one resource.")
@click.option(
	"--expected-checksum",
	multiple=True,
	metavar="KEY=CHECKSUM",
	help="Target checksum from the reviewed dry-run; use KEY= for a new resource.",
)
@click.option("--yes", is_flag=True, help="Confirm a mutating deployment.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def apply(
	context: Any,
	package: Path,
	dry_run: bool,
	selection: tuple[str, ...],
	expected_checksum: tuple[str, ...],
	yes: bool,
	as_json: bool,
) -> None:
	"""Plan PACKAGE, or apply explicitly reviewed selections with --yes."""

	with _site_session(context):
		archive = package.read_bytes()
		preflight = _preflight(archive)
		if preflight.status is PreflightStatus.INCOMPATIBLE:
			_emit({"preflight": preflight.as_dict(), "plan": None}, as_json)
			raise click.ClickException("Package is incompatible with this site.")
		parsed = PackageReader().read(archive)
		selections = _parse_assignments(selection, "selection")
		checksums = _parse_assignments(expected_checksum, "expected checksum", allow_empty_value=True)
		deployment, dependency_checker = _deployment_for(parsed.resources)
		plan = deployment.dry_run(parsed.resources, FrappeTargetReader(), selections, dependency_checker=dependency_checker)
		if dry_run:
			_emit({"preflight": preflight.as_dict(), "plan": plan.as_dict()}, as_json)
			if not plan.ready:
				raise click.ClickException("Deployment is blocked until every issue is resolved.")
			return
		if not yes:
			raise click.ClickException("Refusing to change the target without --yes. Run with --dry-run first.")
		if not plan.ready:
			_emit({"preflight": preflight.as_dict(), "plan": plan.as_dict()}, as_json)
			raise click.ClickException("Deployment is blocked until every issue is resolved.")
		target_reader = FrappeTargetReader()
		snapshot = SnapshotService().capture(parsed.resources, plan, target_reader)
		repository = FrappeInstallationRepository()
		installation = repository.create_installation(parsed, plan, snapshot, _target_environment())
		savepoint = _SavepointGuard(frappe.db, f"config_pack_apply_{frappe.generate_hash(length=12)}")
		savepoint.begin()
		try:
			result = deployment.apply(
				parsed.resources,
				target_reader,
				FrappeResourceExecutor(),
				selections,
				checksums,
				dependency_checker=dependency_checker,
			)
		except ConfigPackError as error:
			savepoint.rollback()
			repository.mark_failed(installation, error)
			frappe.db.commit()
			raise click.ClickException(str(error)) from error
		except Exception:
			savepoint.rollback()
			repository.mark_failed(installation, Exception("Unexpected deployment failure."))
			frappe.db.commit()
			raise
		savepoint.release()
		repository.mark_installed(installation, result)
		frappe.db.commit()
		_emit({"installation": installation.name, "snapshot": installation.snapshot, "result": result.as_dict()}, as_json)


@config_pack.command("drift")
@click.argument("installation")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def drift(context: Any, installation: str, as_json: bool) -> None:
	"""Audit live target state against one installed release."""

	with _site_session(context):
		repository = FrappeInstallationRepository()
		record = repository.get_installation(installation)
		report = DriftService().check(repository.installed_checksums(record), FrappeTargetReader())
		_emit({"installation": record.name, "report": report.as_dict()}, as_json)


@config_pack.command("rollback")
@click.argument("installation")
@click.option("--force", is_flag=True, help="Overwrite resources changed after installation.")
@click.option("--yes", is_flag=True, help="Confirm the rollback.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@pass_context
def rollback(context: Any, installation: str, force: bool, yes: bool, as_json: bool) -> None:
	"""Restore the snapshot for INSTALLATION after explicit confirmation."""

	if not yes:
		raise click.ClickException("Refusing to restore target configuration without --yes.")
	with _site_session(context):
		repository = FrappeInstallationRepository()
		record = repository.get_installation(installation)
		if record.status not in {"Installed", "Partially Rolled Back"}:
			raise click.ClickException("Only installed Config Packs can be rolled back.")
		try:
			snapshot = repository.read_snapshot(record)
			plan = RollbackService().plan(snapshot, repository.installed_checksums(record), FrappeTargetReader())
			repository.mark_rollback_started(record)
			result = RollbackService().execute(plan, FrappeRollbackExecutor(), force=force)
		except ConfigPackError as error:
			repository.mark_rollback_failed(record, error)
			frappe.db.commit()
			raise click.ClickException(str(error)) from error
		repository.mark_rollback_complete(record, result)
		frappe.db.commit()
		_emit({"installation": record.name, "snapshot": record.snapshot, "result": result.as_dict()}, as_json)


@contextmanager
def _site_session(context: Any) -> Iterator[None]:
	"""Connect a Bench command to exactly the site passed through ``--site``."""

	frappe.init(site=get_site(context))
	frappe.connect()
	try:
		yield
	finally:
		frappe.destroy()


def _preflight(archive: bytes):
	return PackagePreflightService().inspect(archive, _target_environment(), FrappeDependencyTarget())


def _deployment_for(resources: list[dict[str, Any]]):
	dependencies = DependencyEngine()
	target = FrappeDependencyTarget()
	return (
		DeploymentService(),
		lambda payload: dependencies.missing_for_payload(payload, resources, target),
	)


def _parse_assignments(
	assignments: tuple[str, ...], label: str, *, allow_empty_value: bool = False
) -> dict[str, str | None]:
	"""Parse repeated ``KEY=VALUE`` options without accepting ambiguous input."""

	parsed: dict[str, str | None] = {}
	for assignment in assignments:
		key, separator, value = assignment.partition("=")
		if not separator or not key or (not value and not allow_empty_value):
			raise click.BadParameter(f"{label} must use KEY=VALUE.")
		if key in parsed:
			raise click.BadParameter(f"{label} was supplied more than once for {key!r}.")
		parsed[key] = value if value else None
	return parsed


def _emit(payload: Mapping[str, Any], as_json: bool) -> None:
	if as_json:
		click.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
		return
	for key, value in payload.items():
		if isinstance(value, (dict, list)):
			click.echo(f"{key}: {json.dumps(value, sort_keys=True, default=str)}")
		else:
			click.echo(f"{key}: {value}")


commands = [config_pack]
