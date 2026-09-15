"""Format constants and conservative limits for untrusted package input."""

PACKAGE_EXTENSION = ".fpack"
FORMAT_VERSION = "1.0"

# Limits apply before JSON is parsed. They make archive inspection safe without
# extracting any member to the filesystem.
MAX_ARCHIVE_MEMBERS = 1_000
MAX_MEMBER_SIZE = 5 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_SIZE = 50 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

MANIFEST_PATH = "manifest.json"
CHECKSUMS_PATH = "meta/checksums.json"

IRRELEVANT_Frappe_METADATA = frozenset(
    {
        "creation",
        "modified",
        "modified_by",
        "owner",
        "idx",
        "_user_tags",
        "_comments",
        "_assign",
        "_liked_by",
    }
)
