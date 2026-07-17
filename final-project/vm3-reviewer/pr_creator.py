from shared.github_client import GitHubClient

github = GitHubClient()


def create_pr(
    repo: str,
    issue_number: int,
    branch_name: str,
    issue_title: str,
    impl_summary: str,
    review_result: dict,
    test_output: str,
) -> str:
    issues_md = (
        "\n".join(f"- ⚠️ {i}" for i in review_result.get("issues", []))
        or "Ninguno"
    )
    suggestions_md = (
        "\n".join(f"- 💡 {s}" for s in review_result.get("suggestions", []))
        or "Ninguna"
    )

    pr_body = f"""## 🏭 Software Factory — PR Automático

**Closes #{issue_number}**

### Qué se hizo
{impl_summary}

### Revisión de código
{review_result.get("summary", "")}

**Issues bloqueantes:** {issues_md}

**Sugerencias:** {suggestions_md}

### Tests
```
{test_output[:600]}
```

---
*Auto-generado por el Software Factory · Solo revisar y hacer merge*
"""

    pr = github.create_pr(
        repo=repo,
        title=f"fix: {issue_title} (closes #{issue_number})",
        body=pr_body,
        head=branch_name,
    )
    pr_url = pr.get("html_url", "")

    github.post_comment(
        repo, issue_number,
        f"## ✅ Factory completado\n\n"
        f"**PR listo para review:** {pr_url}\n\n"
        f"{review_result.get('summary', '')}\n\n"
        f"Tests pasan ✓ — solo revisar y mergear.",
    )

    return pr_url
