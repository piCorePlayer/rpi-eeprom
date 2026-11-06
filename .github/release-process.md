# piCorePlayer release automation

The Version Check workflow runs daily and can also be started manually on
`pCP`. It fetches only upstream `apt/*` tags and processes new versions in
version order, one at a time. Each version must descend from the preceding
upstream release; the workflow merges the exact tagged commit, updates the
package version, and atomically pushes the branch and `v<version>-pCP` tag.
It then builds the extension from that tag and publishes its release before
moving on to the next version. Unrelated upstream tags and newer commits on
upstream's default branch are not used.

The highest existing `v<version>-pCP` tag is the baseline. Older missing tags
are deliberately not backfilled: merging them into the current branch would
not reproduce their historical content. The matching upstream baseline tag
must still exist and be an ancestor of `pCP`. If upstream release histories
diverge, a tagged commit is already incorporated ahead of its release, or a
merge conflicts, the workflow stops for manual investigation.

If publication fails after a tag is pushed, the next check resumes that
baseline release, including a partially uploaded draft, before processing
newer tags. Published releases are left unchanged. The Release Extension
workflow can also resume an existing tag manually; it never replaces a
published release. Release creation uses the `RPI_EEPROM_RELEASE` secret,
which needs permission to write repository contents.

To test without publishing, run the **Test pCP Release Pipeline** workflow
(`test_pcp_release.yml`) manually on `pCP`, or run
`python3 -m unittest discover -s test -p 'test_release_pipeline.py'` locally.
These tests use temporary Git repositories and mocked packaging and GitHub
commands; they do not push to GitHub or create real releases. The upstream
`test.yml` workflow is not used for pCP release testing.
