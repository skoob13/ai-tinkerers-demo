# Exception demos

These scenarios exercise application failures using synthetic accounts and ordinary user actions. They do not inject exception events or contain a deliberate throw. Both failing paths are left in place so Self-driving can propose a fix.

## Setup

Deploy this revision with `NEXT_PUBLIC_POSTHOG_KEY` and `NEXT_PUBLIC_POSTHOG_HOST` configured at build time. Enable the Error tracking new-issue responder in the same PostHog project and connect this repository. Confirm the SDK initializes before triggering either scenario. The app captures unhandled promise rejections and forwards React error-boundary failures with `captureException`.

Open `/demo` on HTTPS or localhost. Use one browser tab at a time: selecting a scenario replaces that origin's simulated login in local storage. These are fixed synthetic accounts with reserved `example.com` addresses. Each account adds `demo_scenario` and `demo_synthetic` properties to captured events. No credentials or real user records are involved.

## Clipboard permission denied

1. Choose **Open clipboard scenario**. This restores Robin Demo and opens the file detail page inside a same-origin frame.
2. In the embedded workspace, choose **Share**, then **Copy**.
3. The frame's `clipboard-write 'none'` permissions policy makes the browser reject the real Clipboard API call. The current copy handler does not handle that rejection and records success before copying succeeds.
4. Find the `NotAllowedError` in Error tracking with `demo_scenario = clipboard-permission-denied`, then follow the corresponding Self-driving report.

Use Chromium for the demo because support for the clipboard permissions-policy directive varies between browsers. This models a restricted embedded workspace without changing the browser's persistent permission settings or mocking its APIs. A regular top-level file page remains the control case.

Expected repaired behavior: copying succeeds when allowed; rejection leaves a usable manual-copy option and a clear message, with no unhandled rejection or false success event.

## Missing display name

1. Return to `/demo` and choose **Open profile scenario**.
2. The fixture restores an account without a `name`, modeling an incomplete legacy profile, and navigates to `/files`.
3. The files page reads `user.name.split(...)` and raises a `TypeError`. The application error boundary captures the actual error and displays a recovery link.
4. Find the issue with `demo_scenario = missing-display-name`, then follow its Self-driving report.

Expected repaired behavior: incomplete profile data does not crash the workspace, and ordinary named accounts continue to display correctly. The fixture should remain usable after a fix as a regression reproduction.

## Reset and verification

Use **Open demo setup**, then **Clear demo account** to remove the simulated login and return to the login page. Close the clipboard frame before switching scenarios. Reloading the missing-name workspace before resetting will reproduce the failure again.

Trigger each scenario once initially. Confirm the exception has the expected account, scenario property, application stack, and Self-driving report before repeating it. Multiple occurrences may group into the same issue; a new report is not guaranteed for every click. A report is evidence of intake, not a guarantee that a PR will be generated.

Session replay and scouts are not required for these scenarios. The exception and its stack are the inputs to Error tracking and its Self-driving responder. Upload production source maps separately if the deployed stack needs symbolication.
