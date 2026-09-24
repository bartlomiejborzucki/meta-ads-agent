# Files as earlier releases wrote them

Copied verbatim from the release tags (`git show v<version>:<path>`): the
shipped examples and templates of each release. `tests/test_compatibility.py`
reads every one with the current code, so "no migration required" in the
changelog is a tested claim, not a hope.

When a release changes a file format, add its files here under the new
version as well, and keep the old ones: a user upgrading from any earlier
release has files shaped like one of these directories.
