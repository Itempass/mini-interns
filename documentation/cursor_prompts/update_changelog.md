# Prompt: Prepare for a new release

Your task is to prepare the project for a new release by updating the `VERSION` file and `CHANGELOG.md`. You should not perform any git operations like committing or tagging.

## 1. Determine the New Version

- Read the content of the `VERSION` file. It's currently a development version (e.g., `0.0.2-dev`).
- The new release version will be the stable equivalent (e.g., `0.0.2`). Note this version for the next steps.

## 2. Gather Changes

### From PR Description Drafts:
- Read all the markdown files **for the current development version only** in the `documentation/PR_description_drafts/` directory.
- These files contain summaries of the major changes for the upcoming release. Synthesize these into a clear list of changes, categorized into `Added`, `Changed`, `Fixed`, etc.

### From Git History:
- To ensure no changes are missed, compare the current `main` branch with the tag of the last release.
- You can find the tag for the last release in `CHANGELOG.md` (e.g., `[0.0.1]`).
- Generate a summary of commits since the last release tag to identify any changes not covered by the PR drafts. You can use a command like `git log v0.0.1..HEAD --oneline` to get a list of commits.
- Add any significant changes from this list to your summary.

## 3. Update CHANGELOG.md

Perform the following edits to `CHANGELOG.md`:

1.  **Update Version Heading:** Change the `## [Unreleased]` section title to `## [X.X.X] - YYYY-MM-DD`, using the new version number and the current date.
2.  **Add New "Unreleased" Section:** Add a new `## [Unreleased]` section at the top of the file for future changes.
3.  **Populate Changes:** Under the new version heading, add the summarized list of changes you gathered in step 2. Organize them under `### Added`, `### Changed`, `### Fixed`, etc.
4.  **Update Comparison Links:** At the bottom of the file, update the comparison links. For a new version `0.0.2` and a previous version `0.0.1`, it should look like this:

    ```markdown
    [Unreleased]: https://github.com/Itempass/mini-interns/compare/v0.0.2...HEAD
    [0.0.2]: https://github.com/Itempass/mini-interns/compare/v0.0.1...v0.0.2
    ```
    Make sure to adjust the link for the previous version as well.


## 4. Check main branch for any updates that were not done through PR

1. Use a command like `git log v0.0.1..HEAD --oneline --first-parent --no-merges | cat` to find which commits were not done through the conventional PR way
2. Read the diff for each commit one by one. After reading it, check the CHANGELOG. If the change isn't in the changelog and it is a change that should be in there, append the changelog. 
3. Do this for each commit, one by one.

## 5. Update VERSION file

- Open the `VERSION` file.
- Replace the development version (e.g., `0.0.2-dev`) with the new stable version (e.g., `0.0.2`).

## IMPORTANT

Your final output should be the proposed changes to `VERSION` and `CHANGELOG.md`. **Do not execute the git commands `commit` or `tag`.** 