---
description: Perform a comprehensive code review of the current changes
---

# Code Review Workflow

1. **Analyze Changes**: Identify all files modified in the current branch compared to `main`.
2. **Security Audit**: Scan the changes for hardcoded secrets, SQL injection risks, or insecure data handling.
3. **Architecture Check**: Ensure new components follow the project's folder structure and naming conventions.
4. **Consistency**: Check if new code uses existing utility functions instead of re-implementing logic.
5. **Generate Artifact**: Create a Markdown artifact titled "Code Review Report" with:
    - **Summary**: A high-level overview of the changes.
    - **Critical Issues**: Items that must be fixed before merging.
    - **Suggestions**: Minor style or optimization improvements.
    - **Positive Notes**: Mention particularly clean or well-implemented sections.