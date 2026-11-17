# Milestone 2B - Hardening, Verification, and Open-Source Readiness

## Scope

Milestone 2B hardens the Milestone 2A CheerpJ artifact builder and turns
runtime verification into evidence instead of assumption. The work covers:

1. Safe and transactional `--force` artifact replacement.
2. Explicit lifecycle states separating static prediction, build output, and
   browser execution.
3. GitHub Actions CI on hosted runners with pinned fixtures.
4. Stronger Playwright verification with visual assertions, game-specific input,
   console diagnostics, and retained failure evidence.
5. Open-source documentation, security guidance, and licensing corrections.

Out of scope: TeaVM/SwingJS artifact generation, dashboards, databases, public
APIs, and automatic merging.

## Safe Transactional Builds

Before 2B, a forced build could delete an output directory before knowing
whether the new build would succeed. A mis-specified output path could also
overlap the source archive.

`provikom_converter/build_safety.py` now:

- Resolves and validates source/output paths before deletion.
- Rejects output equal to the source JAR, the source JAR's parent, any source
  ancestor, filesystem roots, existing output symlinks, and symlink components
  that escape validation.
- Builds into a temporary sibling directory.
- Publishes atomically after a successful build.
- Preserves and restores the prior artifact if publishing fails.
- Cleans temporary directories and refuses non-empty overwrite without
  `--force`.

Regression coverage is in `tests/test_build_safety.py`, including dangerous
paths, symlink rejection, failed-force preservation, and successful forced
replacement.

## Lifecycle Model

`provikom_converter/lifecycle.py` defines:

| State | Meaning |
|---|---|
| `analyzed` | Static analysis completed; no artifact. |
| `candidate` | Static analysis predicts buildability; no artifact. |
| `built` | Artifact generated successfully; no execution evidence. |
| `runtime_verified` | Browser checks confirmed rendered UI and interaction. |
| `failed` | Browser execution or verification failed. |
| `unsupported` | Selected backend cannot target the archive. |

Static compatibility reports emit `analyzed`. Artifact manifests move from
schema `1.0` to `1.1` and emit `built` with `verification.state = "not_run"`.
`verification.json` is created only from browser evidence and is referenced by
the manifest lifecycle block. The static `compatibility` block is never rewritten
to imply runtime success.

Schema compatibility:

- `schema/compatibility-report.schema.json` keeps 2A required fields and adds
  optional lifecycle metadata.
- `schema/artifact-manifest.schema.json` accepts `1.0` manifests without a
  lifecycle block and requires lifecycle only for `1.1`.

## Browser Verification

`tests/test_browser_smoke.py` now verifies more than canvas existence:

- Pillow analyzes canvas screenshots for unique colors, luminance variance,
  non-dark content, and game-specific color distributions.
- CarTraffic verifies the purple menu and performs character selection plus
  NEXT navigation, asserting a large visual change.
- Flappy verifies the sky-blue menu and clicks PLAY, asserting the gameplay UI
  changed.
- PaddleGame verifies the level-select UI, checks `AbsoluteLayout.jar` Range
  serving, and clicks Easy to assert the game UI changed.
- PongGame asserts `status=error`, the "Java Runtime Error Detected" overlay,
  and the known `No line matching interface Clip` diagnostic.
- Verification captures console diagnostics and uncaught browser errors.
- In strict mode, missing fixtures, Playwright, Pillow, or CheerpJ CDN access
  fail instead of skipping.
- Pong's artifact is retained under `build/verification/pong` for debugging.

Evidence from the latest local run:

| Game | Lifecycle | Key evidence |
|---|---|---|
| CarTraffic | `runtime_verified` | Menu `unique_colors=2287`, `purple_ratio=0.777`; character/NEXT visual change ratio `0.607`. |
| Flappy | `runtime_verified` | Menu `sky_blue_ratio=0.619`; PLAY visual change ratio `0.198`. |
| PaddleGame | `runtime_verified` | Level select `unique_colors=6534`; Easy-mode visual change ratio `0.978`; non-fatal audio diagnostic captured. |
| PongGame | `failed` | `status=error`; `Java Runtime Error Detected`; `No line matching interface Clip`; artifact retained. |

Authored evidence:

- `docs/verification/cartraffic.json`
- `docs/verification/flappy.json`
- `docs/verification/paddle-game.json`
- `docs/verification/pong-game.json`
- `docs/screenshots/cartraffic_running.png`
- `docs/screenshots/cartraffic_interaction.png`
- `docs/screenshots/flappy_menu.png`
- `docs/screenshots/flappy_running.png`
- `docs/screenshots/flappy_interaction.png`
- `docs/screenshots/paddle_running.png`
- `docs/screenshots/paddle_interaction.png`
- `docs/screenshots/pong_audio_error.png`

Flappy keyboard events were dispatched after focus, but the local headless run
showed no visual delta. The asserted Flappy interaction is the PLAY click; the
record explicitly reports the keyboard visual-change ratio rather than claiming
a response.

## CI

`.github/workflows/ci.yml` adds two jobs:

- `python-tests`: Python 3.9 and 3.12 matrix, pinned `project-2024` fixture
  checkout, archive/build-safety tests, artifact and Range tests, and the full
  non-browser suite with strict fixtures.
- `browser-smoke`: Python 3.12, Playwright Chromium, pinned fixtures, strict
  browser execution, and evidence upload for screenshots, verification records,
  and retained Pong artifacts.

Security properties:

- GitHub-hosted ephemeral runners only.
- `permissions: contents: read`.
- No persisted checkout credentials.
- Pinned fixture repository commit
  `cf35f7def1333bf05b3de22206e803567bc7de3b`.
- Concurrency cancellation for superseded runs.
- Missing fixtures/browser dependencies/CDN access fail hard.

Remote GitHub Actions status is reported on the pull request. Local
equivalents passed (see below).

## Verification Results

Commands run locally:

```bash
PROVIKOM_GAMES_DIR=/path/to/project-2024/games \
PROVIKOM_REQUIRE_FIXTURES=1 PROVIKOM_SKIP_BROWSER=1 \
python3 -m unittest discover -s tests -v
# Ran 87 tests, OK (4 browser classes skipped)

PROVIKOM_GAMES_DIR=/path/to/project-2024/games \
PROVIKOM_REQUIRE_FIXTURES=1 PROVIKOM_REQUIRE_BROWSER=1 \
python3 -m unittest discover -s tests -v
# Ran 93 tests, OK, 0 failures, 0 skips
```

Additional focused runs:

```bash
python3 -m unittest tests.test_build_safety -v
python3 -m unittest tests.test_lifecycle -v
python3 -m unittest tests.test_schema_validation -v
python3 -m unittest tests.test_browser_smoke -v
```

## Demo Rebuild

The committed demos were rebuilt with manifest schema `1.1` and lifecycle
records applied from browser evidence. CarTraffic, Flappy, and PaddleGame are
`runtime_verified`; PongGame is `failed` and retains its error evidence.

## Open-Source and Licensing Notes

- README clone URL corrected to
  `https://github.com/AsistenProvikom/java-converter.git`.
- README distinguishes CheerpJ's proprietary runtime from this repository's MIT
  source license.
- `project-2024` contains no LICENSE or NOTICE file. The bundled demo JARs and
  game screenshots are third-party assets and are not relicensed by this
  project's MIT license. Redistribution requires permission from the rights
  holders. A fully publishable release should replace or remove them.
- Public deployments should use a static host with HTTP Range support rather
  than the development preview server.
- Untrusted pull requests must not run on privileged self-hosted runners with
  internal network access.

## Known Limitations

- PongGame audio remains incompatible with browser `Clip` support.
- PaddleGame logs a non-fatal `mark/reset not supported` audio exception.
- Java 22 artifacts depend on the experimental Java 25 preview runtime.
- CheerpJ remains a proprietary CDN/enterprise runtime dependency.
- TeaVM and SwingJS artifact generation remain unimplemented.
- Browser verification depends on external CDN availability; CI correctly fails
  rather than skipping when it cannot verify.
