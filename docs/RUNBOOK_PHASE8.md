# Phase 8 runbook: from the pull request to production

For Din. Every step here is yours: Claude cannot push, open or merge a pull request, start a workflow or touch Cloudflare (the guard denies them). Run the commands in `~/Develop/heartbeat`. When a step's result differs from what is written, follow that step's "If it differs". Your rewrite of the case study prose does not hold up the deploy (Phase 8 settling 13).

## Step 1: push and open the pull request

```bash
git switch phase-8-content
```

```bash
git push -u origin phase-8-content
```

```bash
gh pr create --base main --head phase-8-content --title "Phase 8: content and everything production needs" --body "Goal A of Phase 8: finished cards and README, the case study package, the production gate and the runbook. See docs/WORK_LEDGER.md."
```

Then watch CI:

```bash
gh run list --branch phase-8-content --workflow ci.yml --limit 1
```

Expected: `CI`, `completed`, `success`, with `python`, `web` and `preview` jobs all green. The preview URLs are in the run's job summary, under "Preview for pull request N":

```bash
gh run view --web
```

One of them has the stable form `https://pr-<number>-heartbeat.dineshddawo.workers.dev`. Use it below.

**If it differs:** tell Claude. Claude reads the run with `gh run view` and fixes anything red in a new commit. A red `preview` job with `python` and `web` green points at the Cloudflare secrets, which are yours to check.

## Step 2: preview review

Open the preview URL in Safari or Chrome. To switch theme, change macOS's appearance (System Settings, Appearance): the page follows it.

Full page, in light and in dark:

- The page opens on record 200 and starts in a span with an irregular beat. Under the controls: "Research demo, not medical advice. Recordings come from a public research database."
- It also says: "Record 200 opens first. I picked it before testing, with a rule that reads only the expert labels, because it has many irregular beats."
- Play runs the trace. Letters appear over the beats one beat late. Without loading problems the line reads "Labels match the Python results: N of N beats" and shows no "differ".
- "Next irregular beat" moves the trace and says "Beat at m:ss.s: experts S" or similar. "Next disagreement" says "Beat at m:ss.s: model X, experts Y".
- The recording picker lists 21 records, and a pick loads that record.
- Nothing is cut off at a narrow window.

Then `?embed=page` added to the same URL, in light and in dark:

- No header, footer, picker, position slider or beat table. The research-demo line is there and readable.
- "Open the full demo" opens a new tab, and the embed stays open.

The clip and the capture, from this checkout:

```bash
open docs/case-study/capture.mp4 docs/case-study/capture.jpg
```

Expected: record 200, light theme, the research-demo line readable, no controls cut off. Approving them is your call (G2). Leave a note on the pull request or tell Claude if one needs recording again.

**If it differs:** a demo problem stops here: tell Claude what you saw, in which browser and mode. Claude cannot change the demo's code for the video (stop condition 6), so a clip problem that needs a code change comes back to you as a decision.

## Step 3: VoiceOver and a real phone (R48, launch criterion 3)

Use the preview URL. What matters is the name and the words below; VoiceOver adds its own words around them ("button", "selected") and they vary by version. Write down anything that is missing, wrong or confusing, in your own words: Goal B records it.

### VoiceOver on macOS, in Safari

Start it with Command F5. Move with Control Option Right Arrow. Press with Control Option Space.

| Do | Expected, from the page's labels |
| --- | --- |
| Open the full page, move from the top | "Heartbeat", heading level 1, then a "Live demo" region |
| Move into the trace | An image named like "ECG trace of record 200, 0:20 to 0:30: 12 beats, 2 flagged by the model, all agree with the experts". The name updates on pause and seek, not while it plays |
| Move to the play button, press it | A toggle button named "Play". Pressed, it is named "Pause" and marked pressed. During playback the status line announces politely once per 10 seconds of playback, "Last 10 seconds: 12 beats, 2 flagged, all agree with the experts" or similar, and nothing else talks |
| Press it again to pause | Named "Play" again. The status line announces "Last 10 seconds: 12 beats, 2 flagged, all agree with the experts" or similar |
| Move to Speed | A pop-up named "Speed", showing the current speed such as "1x" |
| Press "Next irregular beat" | A button with that name. VoiceOver announces, without moving focus, "Beat at m:ss.s: experts S" or similar |
| Press "Next disagreement" | Announces "Beat at m:ss.s: model X, experts Y", or "No disagreements in this recording: the model agrees with the experts on every scored beat" |
| Move to Recording | A pop-up named "Recording", showing "Record 200: N N, S S, V V, F F" with the counts |
| Move to Position | A slider named "Position", its value read as "m:ss of m:ss" |
| Move to the list after the controls | A list named "What the marks mean": N Normal, S Supraventricular early beat, V Ventricular early beat, F Fusion beat |
| Move to the beat table | A table with the caption "Beats in view, 0:20 to 0:30" or similar, and columns Time, Model, Estimated probability, Experts, Match |
| Move down | "How it works", heading level 2, then its level 3 headings |

Then add `?embed=page` to the URL and repeat the top of the table. Expected: "Heartbeat" as a heading level 1, the "Live demo" region, the trace image, Play, Speed and both jump buttons. The jump buttons still announce. There is no "Last 10 seconds" line in the embed, no Recording, no Position and no table. "Open the full demo" is a link.

With "Reduce motion" on (System Settings, Accessibility, Display) and the full page reloaded: two more buttons, "Previous 10 seconds" and "Next 10 seconds". Each one moves the trace by 10 seconds and the status line announces the new span.

### VoiceOver on iOS, in Safari

Settings, Accessibility, VoiceOver, on. Open the preview URL. Swipe right to move, double-tap to press.

Walk the same table on the full page and on `?embed=page`. Expected: the same names and the same announcements, in the same order. The trace does not trap the swipe.

### Real phone, with VoiceOver off

On your phone, in Safari, on the full page and on `?embed=page`, in light and in dark:

- The trace appears, then Play runs it smoothly, and letters arrive. The first label may take several seconds on a first visit (the runtime is the bulk of the download).
- Tap every control. Nothing is too small to hit, and nothing overlaps.
- Turn the phone sideways and back. Nothing breaks.
- The research-demo line is readable without zooming.

**If it differs:** a failure on any of these goes to Claude in Goal B before anything else. It holds up launch criterion 3, and you decide whether it holds up the deploy.

## Step 4: merge, then wait for CI on the merge commit

```bash
gh pr merge --merge --delete-branch
```

```bash
git switch main
```

```bash
git pull
```

```bash
gh run list --branch main --workflow ci.yml --limit 1
```

Expected: `CI`, event `push`, for the merge commit, `completed`, `success`. Wait until it says so.

**If it differs:** do not deploy. Tell Claude what is red.

## Step 5: deploy to production

```bash
gh workflow run deploy.yml --ref main
```

```bash
gh run list --workflow deploy.yml --limit 1
```

```bash
gh run watch
```

Expected: the `production` job passes. Its second step, "Refuse a commit whose CI did not pass", prints `CI passed for <sha> (1 successful run or runs).`

**If the gate refuses:** the job stops before anything builds, with one of:

- `Refusing to deploy: no successful ci.yml push run on main for <sha> (gh said: '0').` CI has not passed on that commit. It is still running, or it failed. Wait or fix. Never bypass it.
- `Refusing to deploy: gh could not read CI for <sha>.` `gh` failed in the job. Run it again once; if it repeats, bring it back to Claude.

## Step 6: attach the domain

In the Cloudflare dashboard: Workers & Pages, `heartbeat`, Domains, Add, Custom Domain, `heartbeat.dins.dev`. Your CI token has no zone access and never gets it: this step is the dashboard only (settling 9).

Then, allowing a few minutes for the certificate:

```bash
curl -sI https://heartbeat.dins.dev/
```

Expected: `HTTP/2 200`, and a `content-security-policy` header with `frame-ancestors 'self' https://dins.dev https://*.dineshddawo.workers.dev`.

**If it differs:** a certificate error in the first minutes is normal, so try again. A refusal from Cloudflare (a conflicting record, or the zone not offered) is PRD Q3's answer. Stop and bring it back. Do not add a `routes` key to `web/wrangler.jsonc` or widen the token to get around it.

## Step 7: failure cases

**A deploy that fails on permissions.** The token is Worker Editor with no zone access and has only run `versions upload` so far. Cloudflare's docs say Editor covers a deploy that leaves the domain alone, but this is the first real test of that. If `wrangler deploy` fails with an authorization error, stop and bring the message back. Never widen the token without a decision.

**Rollback.** If production is wrong after a deploy, from a shell logged in with `wrangler login`:

```bash
pnpm -C web exec wrangler rollback
```

Expected: wrangler lists the previous version and asks to confirm. This is yours only. Afterwards, tell Claude what was wrong; the fix goes through a pull request and step 5 again.

## Step 8: what to send Goal B

When `https://heartbeat.dins.dev/` answers 200, start Goal B and give Claude:

- The VoiceOver results: macOS Safari and iOS Safari, full page and `?embed=page`, in your own words. Anything that passed can be one line (R48).
- The real-phone results: which phone, which iOS, light and dark, what you saw.
- How the domain attach went, including any message from Cloudflare (PRD Q3, AS4).
- Anything from the preview review you decided to leave as it is, and your call on the clip and the capture.
