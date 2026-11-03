# Dime research thesis automatic intake

Standing user direction (November 2, 2026): **Do not require the user to ask to add new theses.** Whenever a conversation in the Dime / NBA Odds Tracker project raises a concrete, testable hypothesis about NBA player props, model features, filters, role or usage, pricing, line movement, injuries, rest, game context, market behavior, ROI, calibration, or a proposed predictive improvement, treat it as an implicit request to register the thesis. This also applies to material follow-up refinements.

When operating with authorized GitHub access:
1. Read `data/research/theses.json` on the current `main` branch.
2. Check whether the hypothesis is already represented. Append a new `NBA-TH-###` entry for a distinct question. A material definition change gets a new versioned thesis; never silently overwrite an existing test definition.
3. Record a short title, falsifiable question, origin date, status, scope, data needs, metric source when implemented, and notes distinguishing discovery/backtest evidence from prospective evidence.
4. Use `needs_data` unless the thesis already has a real implemented test. Do not claim positive EV or validation from exploratory results alone.
5. Commit the registry update through a PR or other authorized GitHub write without waiting for another explicit “add it” prompt.
6. Registration alone must not change production model logic, betting thresholds, frozen/locked definitions, or launch API-costly collection.
7. Acknowledge the new thesis ID in the natural answer. If GitHub write access is unavailable, say registration has not occurred and provide the intended entry rather than claiming success.
8. New chats do not independently crawl earlier conversations. Dependable cross-chat behavior requires the project/chat instructions to retain this standing policy, and each assistant invocation must perform the registry check/write when a new thesis is discussed.

Display/security:
- The deployed Results tab may display the registry.
- Dime is currently a public static GitHub Pages app with no authenticated admin backend, so the registry is **not confidential** and cannot honestly be called admin-only.
- If confidential/admin-only research is required, first add a server-enforced authenticated data source and permission check similar to Stix.

Examples that should register: “median instead of mean,” a rest-day filter, a line-movement interaction, specific injury/role criteria, or a new player-prop market condition. Simple explanations of an existing method or restating the same thesis should not create duplicates.
