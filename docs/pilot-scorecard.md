# Pilot scorecard

Start with one infrastructure repository and the documented supported checks.
Use synthetic or company-approved sanitized inputs before enabling any company AI
endpoint. No customer data or application code is needed.

## Measures

| Measure | Definition | Current status |
| --- | --- | --- |
| Supported coverage | Supported changed resources / reviewed changed resources | Record during pilot |
| Reviewer-confirmed findings | Findings marked confirmed by the designated reviewer | Unmeasured |
| False positive rate | Reviewer-marked false positives / adjudicated findings | Unmeasured |
| Review turnaround | Time from review availability to recorded disposition | Unmeasured |
| Explanation usefulness | Reviewer's useful / not useful rating | Unmeasured |
| Review reliability | Complete runs / attempted runs, with errors reported separately | Synthetic verification only |
| Data boundary failures | Canary violations or observed unauthorized data emission | No violations in current regression tests |

A passing synthetic fixture is an engineering check. It does not establish a real
false-positive rate, incidents prevented, money saved or user adoption. Compare
review turnaround against a measured baseline for the same team and workflow.

## Suggested record

Keep pilot records in a private company system. A record can include an opaque
review ID, rule ID, review-ready timestamp, disposition timestamp, classification
(`confirmed`, `false_positive`, `accepted_exception`), and explanation usefulness.
Do not include raw infrastructure, resource names, account IDs, secrets or customer
information in public metrics. Exceptions require their own owner and reason.

## Incremental tasks

1. **45-60 minutes:** add the pinned reusable workflow to a chosen sandbox repository
   and confirm safe, risky and incomplete inputs produce the expected outcomes.
2. **60-90 minutes:** validate an approved company gateway/model from trusted local
   configuration. The owner supplies endpoint policy and credentials privately.
3. **45-60 minutes:** have the designated reviewer classify findings and time the
   review. Keep independent approval for anything beyond the isolated solo demo.
4. **60-90 minutes:** use actual pilot feedback to prioritize the next supported
   resource type, then add positive, negative and incomplete-input tests.

The company gateway and a real pilot remain owner-dependent. No production change,
credential request or new public performance claim is part of this session.
