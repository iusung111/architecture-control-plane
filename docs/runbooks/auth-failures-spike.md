# Authentication failures spike

## Signal
`ACPAuthFailuresSpike`

## What it means
The service is rejecting authentication at an abnormal rate.

## First checks
1. Inspect auth failure reasons in Prometheus and logs.
2. Check IdP/JWKS/discovery reachability and cache freshness.
3. Verify recent token issuer, audience, or signing key changes.

## Mitigation
- Restore the previous IdP configuration if a rollout caused the spike.
- Re-enable header fallback only for controlled emergency scenarios.
- Communicate token issuance problems to the identity team.
