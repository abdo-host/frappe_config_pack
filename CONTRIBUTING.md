# Contributing

Thank you for improving Frappe Config Pack.

## Development setup

Install the app in a Frappe Bench environment, then run the checks from the app directory:

```bash
python -m pytest frappe_config_pack/tests -q
ruff check frappe_config_pack
```

Run `bench --site <site> migrate` after DocType changes and rebuild assets after JavaScript or SCSS changes.

## Contribution rules

- Keep business rules in the core, services, and resource handlers; Desk pages and CLI commands are thin adapters.
- Add automated tests for every behavior change.
- Keep serialization deterministic and preserve the package safety model.
- Do not add remote pull, push, or synchronization behavior.
- Do not serialize credentials, site secrets, or generated business data.
- Keep a pull request focused on one reviewed change.
