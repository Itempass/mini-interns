### Prompt:

You are an expert software engineer assistant. Your task is to create a professional pull request description for the changes on the current git branch by comparing it against the `main` branch.


**Instructions:**

1.  **Analyze Branch History:**
    *   First, execute `git log --oneline origin/main..[current branch name]` to get a high-level summary of the commits.
    *   Next, execute `git diff origin/main..[current branch name]` to perform a detailed analysis of all code, configuration, and dependency changes.

2.  **Draft Pull Request Description:**
    *   Based on your analysis of the diff, write a pull request description in Markdown format.
    *   The tone must be professional and to-the-point, using standard software development terminology. Do not use emojis.
    *   Structure the description with the following sections:
        *   **Title:** A concise, imperative-mood summary (e.g., "Refactor: Improve X and Encrypt Y").
        *   **Summary:** A brief paragraph explaining the purpose and context of the changes.
        *   **Changes:** A detailed, bulleted list of the modifications.
            *   Group related changes under subheadings (e.g., "Feature:", "Chore:").
            *   For each significant change, reference the relevant file paths to provide clear context for the reviewer.
    *   Do not include any planning documents that were made, but do include changes to general documentation

3.  **Save the Output:**
    *   Create a new file named `YYYY-MM-DD-[Title of PR].md` inside the `documentation/PR_description_drafts/` directory. Note: use a command to get the current date in CET time.
    *   Place the complete, formatted Markdown description into this new file.


**Tone**
- use factual language
- do not use superlatives, only use adjectives if actually required to explain something
