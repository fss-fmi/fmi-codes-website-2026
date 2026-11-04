# ADR-012: A relay replies "recovered" under Flux's Slack errors

**Status**: accepted. Extends [ADR-010](010-cluster-alerts-to-slack.md): Flux errors still post through the incoming webhooks; a relay in the cluster adds the recovery.

## Context

ADR-010 posts Flux reconcile errors to Slack and nothing else. The first real post was a transient one: image automation timed out cloning the repo twice, then pushed its bump a minute later. The channel showed an error and nothing after it, so it looked like an open problem. Excluding the timeout would hide the record; the goal is to keep the error and say when it cleared.

Neither sender can do that. Flux's `slack` provider posts each event as a new message, an incoming webhook returns no message `ts` to reply under, and with `eventSeverity: error` Flux forwards no success events at all. Alertmanager's resolved notice is a separate message too.

Reading the controllers running here (notification-controller v1.9.2, kustomize-controller v1.9.3, source-controller v1.9.3, image controllers v1.2.3, helm-controller v1.6.2) showed:

- A `generic` Provider gets every non-trace event, success events included.
- A HelmRelease that comes back in sync without a Helm action sends no event. Waiting for info events would leave such an error open forever.
- notification-controller drops an identical event for 5 minutes only, so a lasting failure posts again about every 5 minutes.
- Every Flux object here lives in `flux-system`, and Flux's own NetworkPolicy admits traffic from that namespace only.

## Decision

- **Errors keep posting through the webhooks**, unchanged. Each Slack Alert gets a `flux-relay` twin with the same sources and exclusions, sending the same errors to a `generic` Provider at the relay's `/cluster` or `/staging` path. A test fails if a twin drifts from its Slack Alert.
- **The relay finds the error's post** by the object and message in that route's channel and keeps the open incident, every post of it, in the ConfigMap `flux-system/flux-relay-state`. It only claims posts for errors its own cluster reported, so two clusters sharing a channel don't close each other's.
- **Recovery is read from the object**, the `Ready` condition every 15 seconds, not from info events. An error that never made the object unready closes after 15 quiet minutes.
- **On recovery**: one thread reply under the first post and a ✅ reaction on every post of the incident. A deleted object gets its own reply.
- **No image to build.** The relay is one stdlib Python file in a kustomize `configMapGenerator`, on `python:3.12-slim` pinned by digest, deployed by its own Flux Kustomization. Role-only RBAC: `get` on the eight Flux kinds and get/patch on its state ConfigMap.
- **Its own Slack app and Secret.** The Flux Relay app has only `channels:history`, `chat:write` and `reactions:write`, separate from the CI bot so the cluster never holds a token that reaches the GitHub channels. Its token and the two channel IDs live in `flux-system/flux-relay-slack`, one SOPS file per env, handled like the other cluster-wide Secrets (env label and guard, `rotate-secret.sh --flux-relay`, bootstrap pre-flight). One Secret per workload, rather than new keys in `alertmanager-slack`, keeps the token off Alertmanager's disk.

## Consequences

- **Easier**: a Flux error in the channel says whether it still needs attention. A transient error can stay posted instead of being excluded, which makes the network-blip exclusions worth revisiting.
- **Harder**: one more workload, Slack app, token and SOPS file per env to rotate, fork and hand over. Slack is read on every new error.
- **Failure mode**: if the relay is down or has no token, errors post exactly as before and only the reply is missing. An incident open while the relay is down is replied to when it comes back, from the ConfigMap.
- **Later**: Alertmanager's resolved notices could be threaded the same way through a webhook receiver; out of scope here.
