# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's **Security** tab using a private vulnerability report, if that feature is enabled for this repository. Include a concise description, affected paths or versions, reproduction steps, impact, and any safe remediation ideas.

If private vulnerability reporting is unavailable, open a minimal public issue asking the maintainers to provide a private reporting channel. Do not include exploit details, credentials, tokens, private application data, or authenticated browser artifacts in a public issue.

No dedicated security email address or response-time commitment is published in this repository.

## Sensitive data rules

Do not commit, upload, paste into issues, or include in test evidence:

- `.env` files;
- LLM or other API keys;
- usernames or passwords;
- access, refresh, or session tokens;
- cookies or Playwright storage-state files;
- authenticated screenshots, traces, videos, HAR files, console logs, or browser artifacts that reveal private data;
- execution reports or application maps until their contents have been reviewed and redacted.

Use disposable test accounts and least-privilege credentials. Supply secrets at runtime through an approved secret store or local environment, never through source code, image layers, prompts, generated tests, or committed configuration.

If a credential or authenticated state is exposed, revoke or rotate it immediately. Removing the file in a later commit is not sufficient because Git history and downloaded artifacts may retain it.

## Project security boundaries

- Generated tests are untrusted until deterministic grounding checks accept them.
- Grounding reduces unsupported literals but is not a complete sandbox or semantic verifier.
- Model-assisted RCA is advisory and must not be treated as authoritative security analysis.
- Browser state and execution artifacts can remain sensitive even when they contain no plaintext password.
- Running generated/external tests executes Python against an external application; review the generated source and target environment before opting in.

Security fixes should include deterministic regression tests where practical and should avoid adding real exploit data or credentials to fixtures.
