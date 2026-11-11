# Planned work

This page lists each feature of the harness that is planned or that is work in progress. The
other pages describe each feature where it belongs, and mark it *planned* or *work in progress*.
Each such mark links its row on this page, and each row links the section that describes the
feature. When a feature lands, its row and its marks go in the same change.
`npm run docs:check` fails when a mark has no row or a row has no mark
([Development](development.md#the-documentation-site)).

## Sandboxes and safeguards

| feature | state | described in |
|:--|:--|:--|
| **A guard against a session with no sandbox**{#no-sandbox-guard} | planned | [Sandboxes](safeguards/sandbox.md#planned), [The security model](safeguards/security-model.md#planned-safeguards) |
| **Fewer prompts under the launcher**{#fewer-prompts} | planned | [Sandboxes](safeguards/sandbox.md#planned) |
| **The desktop apps under an outer sandbox**{#desktop-apps} | planned | [Sandboxes](safeguards/sandbox.md#planned), [The security model](safeguards/security-model.md#planned-safeguards) |
| **The launcher on Linux**{#linux-launcher} | planned | [Sandboxes](safeguards/sandbox.md#planned), [The security model](safeguards/security-model.md#planned-safeguards) |
| **The daemon profiles on Linux**{#daemon-profiles-linux} | work in progress | [Sandboxes](safeguards/sandbox.md#the-daemon-profiles), [The security model](safeguards/security-model.md#planned-safeguards) |
| **Masked keys**{#masked-keys} | planned | [Sandboxes](safeguards/sandbox.md#planned), [The security model](safeguards/security-model.md#planned-safeguards) |
| **A forge token per owner**{#token-per-owner} | planned; waits for your tokens | [Sandboxes](safeguards/sandbox.md#planned), [The security model](safeguards/security-model.md#planned-safeguards) |
| **Kaimon without the network**{#kaimon-without-network} | planned; waits for [the daemon profiles on Linux](#daemon-profiles-linux) | [Sandboxes](safeguards/sandbox.md#planned), [The security model](safeguards/security-model.md#planned-safeguards) |
| **A credential proxy**{#credential-proxy} | planned; optional and last | [Sandboxes](safeguards/sandbox.md#planned), [The security model](safeguards/security-model.md#planned-safeguards) |

## Static checks

| feature | state | described in |
|:--|:--|:--|
| **Rules of medium risk**{#medium-risk-rules} | planned | [Static checks](agentic/static-checks.md#planned-checks) |
| **Checks that load the code**{#checks-that-load-code} | planned | [Static checks](agentic/static-checks.md#planned-checks) |
| **A catalogue of defensive Julia**{#defensive-julia} | planned | [Static checks](agentic/static-checks.md#planned-checks) |

## Tests and CI

| feature | state | described in |
|:--|:--|:--|
| **A regression set for the critics**{#critic-regression-set} | work in progress | [Tests and CI](agentic/tests-and-ci.md#planned) |
| **Tests of the dependents**{#dependent-tests} | planned | [Tests and CI](agentic/tests-and-ci.md#planned) |
| **Property-based tests**{#property-based-tests} | planned | [Tests and CI](agentic/tests-and-ci.md#planned) |

## The edge catalogue

| feature | state | described in |
|:--|:--|:--|
| **The removal of catalogue entries**{#edge-removal} | planned | [Edges](agentic/edges.md#the-limits) |
