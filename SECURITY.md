# Security Policy

Assembly is experimental software that calls third-party model and optional search APIs. Please report security issues responsibly and give maintainers a chance to investigate before public disclosure.

## Reporting a vulnerability

**Do not open a public GitHub issue or pull request for a suspected vulnerability.**

Preferred method, once enabled: open the repository's **Security** tab and use **Report a vulnerability** to submit a private report. GitHub private vulnerability reporting is a repository setting; the maintainers must enable it after the repository is made public. If the private report button is not available, contact the maintainer privately through the contact method listed on the maintainer's GitHub profile. Do not publish exploit details while arranging contact.

A useful report includes the affected commit or version, deployment/configuration context, impact, reproduction steps, and a minimal proof of concept. Redact keys, tokens, personal data, and any information belonging to other users. Test only systems and accounts you own or are explicitly authorized to assess.

Please allow maintainers reasonable time to confirm the issue, assess impact, prepare a fix, and coordinate disclosure. Do not assume a report has been received until you get an acknowledgement.

## Exposed API keys or credentials

If a real key or credential may have been exposed:

1. Revoke or rotate it immediately in the relevant provider or service dashboard. Deleting the text from a commit is not enough.
2. If it entered Git history, logs, CI output, screenshots, a browser capture, an issue, or a pull request, describe the exposure privately without repeating the secret.
3. Remove the secret from the affected location, inspect related logs/artifacts, and determine whether other credentials could have been exposed.
4. Never send a live key to maintainers as part of a report. Use a short masked prefix/suffix or a newly generated disposable test key where necessary.

Contributors must not commit `.env`, tokens, provider keys, browser storage exports, production logs, or realistic secrets in test fixtures. Report accidental exposure promptly even if the credential has already been rotated.

## Supported versions

Until Assembly publishes a stable, versioned release policy, **the current `main` branch is the primary supported development line**. A published release is supported only if its release notes explicitly say so. Old commits, forks, and unmaintained deployments may not receive fixes. Users should update to the latest supported code before reporting a vulnerability.

## Scope and limitations

Assembly does not guarantee factual correctness, model independence, or suitability for high-stakes use. A model/provider vulnerability should also be reported to the relevant provider when appropriate. Denial-of-service testing, credential attacks, or testing against other people's deployments without permission are not authorized by this policy.
