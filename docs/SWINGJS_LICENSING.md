# SwingJS / Java2Script Licensing Review

This is an engineering review, not legal advice. The purpose is to identify
what the Milestone 2C.0 build actually contains and to keep the project from
treating MIT as permission to redistribute third-party runtime components.

## Reviewed Revision

All observations below refer to:

- Repository: `https://github.com/BobHanson/java2script.git`
- Commit: `4091b289014b99099481c37f7c151aeb24c713cd`
- Java2Script compiler plug-in: `j2s.core.jar`, version `5.0.1`
- SwingJS runtime archive: `SwingJS-site.zip`, version `5.0.1-v7`

Pinned hashes:

| Artifact | SHA-256 |
|---|---|
| `LICENSE.txt` | `b3bffcae3b9483cb91aefb6a4fb2fcacef8f9ac5bf7ac505000bc1b7a2a2ed5e` |
| `j2s.core.jar` | `81dbd7dbbc1f9eff90d3a47c48d3625b135ab8c3a12345d491f41a0bc6dbd76a` |
| `SwingJS-site.zip` | `2b275f7c1bbd420aa79a5831a1fd2d9e4b3dd75079f0f2eb8fe29d13e0d4cec0` |

## What the Upstream Licenses Say

### Java2Script / SwingJS

The repository `LICENSE.txt` says Java2Script/SwingJS is distributed under
**GNU GPL version 2 with the Classpath Exception**. It also states that the
project was originally EPL 1.0, that code from other sources was added,
including OpenJDK code under GPL+CE, and that contributors agreed to move to
GPL+CE.

The repository is not uniformly headed, however:

- The root license is GPLv2+CE.
- Some Java source files still carry EPL 1.0 headers.
- `sources/net.sf.j2s.java.core/src` contains an Apache License 2.0 file and an
  Apache Harmony `NOTICE`.
- The runtime archive includes `swingjs/j2s/org/json/LICENSE`, the JSON.org
  license.

These are component-level questions, not a single clear license for the whole
distribution.

### Bundled JSON library

`SwingJS-site.zip` includes the JSON.org license:

- Copyright (c) 2002 JSON.org.
- Permission is granted to use, copy, modify, merge, publish, distribute,
  sublicense, and sell, provided the copyright and permission notice are
  included.
- The Software shall be used for Good, not Evil.
- The software is provided without warranty.

The JSON license is not the same as MIT, Apache 2.0, GPL, or EPL. The
"Good, not Evil" condition is a use restriction that some organizations treat
as non-standard or non-free. If the runtime is redistributed, the JSON
copyright and license text must travel with it.

### Apache Harmony / Apache 2.0

The Java core source tree includes an Apache 2.0 `LICENSE` and an Apache
Harmony `NOTICE` identifying Apache Software Foundation and Intel
contributions. The built SwingJS runtime archive does not contain those
notice files. Apache 2.0 redistribution generally requires retaining
copyright, license, and NOTICE information for redistributed components.

### Eclipse and the JDK

The build uses Eclipse 2024-03 and Temurin JDK 17 as external tools. They are
not copied into the generated SwingJS site. If a future distribution bundles
either tool, their own licenses and notices apply.

### CheerpJ

CheerpJ is a proprietary Leaning Technologies runtime. The benchmark loads it
from the official CDN. This repository does not redistribute CheerpJ or grant
any rights to it.

## Current Artifact Contents

The generated deployable site contains:

- The generated `poc_SwingPoc.html` entry page.
- Generated application JavaScript at
  `swingjs/j2s/poc/SwingPoc.js`.
- The SwingJS runtime and transpiled Java class library under
  `swingjs/j2s/`.
- `swingjs/j2s/org/json/LICENSE`.

It does **not** currently contain:

- The Java2Script root `LICENSE.txt`.
- The Apache Harmony `NOTICE`.
- The Apache 2.0 license text.
- A separate notice for OpenJDK-derived material.
- A clear statement of which files are GPL+CE, EPL, Apache, or JSON licensed.

The generated site is therefore not ready to be published as a compliant
third-party runtime distribution.

## Redistribution Position

| Component | Current handling | Redistribution status |
|---|---|---|
| POC source in `examples/swing-poc` | Committed, authored for this project | Covered by repository licensing; no third-party runtime included |
| Generated `SwingPoc.js` and HTML | Local/CI evidence only | Characterization depends on runtime-derived output; legal review required before publishing |
| `j2s.core.jar` compiler plug-in | Downloaded to ignored `build/` | GPLv2+CE with mixed component history; do not commit or redistribute without compliance review |
| `SwingJS-site.zip` runtime | Downloaded to ignored `build/` | GPLv2+CE plus Apache/JSON components; missing notices; do not commit or publish as-is |
| Full generated SwingJS site | Ignored `build/` output | Treated as a local test artifact until licensing is resolved |
| Eclipse and JDK | External toolchain only | Not redistributed by this project |
| CheerpJ | CDN benchmark dependency only | Proprietary; not redistributed |

## Required Work Before Publishing Generated Artifacts

1. Obtain a legal review of GPLv2+CE, EPL 1.0 file headers, Apache Harmony
   notices, OpenJDK-derived files, and the JSON license as they apply to the
   exact generated output.
2. Decide whether generated JavaScript is a derivative work of the runtime,
   a separate application, or a combined work.
3. If GPL-covered binaries are distributed, satisfy source-availability and
   notice obligations for the corresponding GPL components.
4. Include the Java2Script `LICENSE.txt`, Apache 2.0 `LICENSE`, Apache Harmony
   `NOTICE`, JSON license, and any OpenJDK notices required by counsel.
5. Add a generated NOTICE/SBOM step so every published artifact identifies its
   runtime files and licenses.
6. Do not use the repository's MIT license as a substitute for runtime
   licenses.

## Current Policy for Milestone 2C.0

- Keep generated SwingJS sites under ignored `build/` directories.
- Do not commit Java2Script, SwingJS, Eclipse, JDK, or CheerpJ binaries.
- Do not upload the complete runtime/site from CI. The workflow uploads only
  source-derived POC output, logs, hashes, screenshots, and verification JSON.
- Do not publish a SwingJS demo or gallery artifact.
- Revisit this policy before Milestone 2C.1 produces a distributable artifact.

The unresolved licensing questions are a condition of the **CONDITIONAL GO**
decision, not a reason to claim the toolchain is ready for production
distribution.
