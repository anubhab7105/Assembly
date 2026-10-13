# Security Policy

Assembly handles user-supplied questions and provider credentials, and depends on external services. Security reports are welcome. Please help us fix issues responsibly.

## Report a vulnerability privately

**Do not disclose an unresolved vulnerability in a public issue, discussion, pull request, or social post.**

Preferred route, once enabled: open the repository's **Security** or **Security and quality** tab and select **Report a vulnerability** to submit a private GitHub security advisory. The private reporting form is separate from this file and must be enabled in repository settings by an owner or administrator.

If the private reporting option is not available, use the maintainer's private contact channel listed on the [GitHub profile](https://github.com/anubhab7105) and ask for a secure disclosure route. Do not attach exploit details or secrets to a public issue.

A useful report includes:

- A concise summary and affected component/commit or release.
- Impact, preconditions, and realistic attack scenarios.
- Minimal, safe reproduction steps or a proof of concept that does not access other people's data.
- Any relevant sanitized logs, request/response details, and a suggested mitigation if known.

Please allow the maintainer time to investigate and coordinate a fix before public disclosure. Do not test against systems or data you do not own or have permission to test.

## If an API key or secret is exposed

Treat an exposed key as compromised, even if it was removed from the latest commit.

1. Revoke or rotate the key at the provider immediately; create a replacement and update your local secret store.
2. Check provider usage and billing for unexpected activity.
3. Remove the value from tracked files and, if appropriate, coordinate a history rewrite. History cleanup does **not** make the old key safe; rotation is the priority.
4. If the exposure occurred in Assembly itself, privately notify the maintainer with the provider, approximate exposure time, and affected locations. Do not send the replacement secret.
5. Never paste active keys into an issue, pull request, log, screenshot, test fixture, or support message.

For a key leaked from your own fork or development environment, rotate it first and review your own logs and deployment environment.

## Supported versions

Assembly is currently pre-1.0 and does not promise stable APIs or release branches.

- **Supported:** the latest commit on **main** and the latest official release, if one is published.
- **Not supported:** older commits, unmaintained forks, and prerelease builds that have been superseded.
- Security fixes are not guaranteed to be backported to older versions. Upgrade to the latest supported version when practical.

## Scope and limitations

Reports are most useful when they demonstrate a security impact in Assembly's code, configuration, or documented deployment path. A provider outage, rate limit, or vulnerability wholly within a third-party service should be reported to that provider, though a security consequence caused by Assembly's handling may still be relevant.

No bug-bounty program or response-time SLA is currently promised.
