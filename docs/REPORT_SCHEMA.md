# Provikom Converter - JSON Compatibility Report Specification

## Schema Identification
- **Schema URI**: `https://provikom.org/schema/v1/compatibility-report.json`
- **Specification**: JSON Schema Draft-07
- **Schema File**: [schema/compatibility-report.schema.json](../schema/compatibility-report.schema.json)
- **Artifact Manifest Schema**: [schema/artifact-manifest.schema.json](../schema/artifact-manifest.schema.json)

---

## Top-Level Structure

A valid report contains eight mandatory top-level sections:

```json
{
  "schema_version": "https://provikom.org/schema/v1/compatibility-report.json",
  "metadata": { ... },
  "archive_summary": { ... },
  "manifest": { ... },
  "class_file_info": { ... },
  "features_detected": { ... },
  "backend_compatibility": { ... },
  "recommendation": { ... },
  "lifecycle": { ... }
}
```

---

## Field Reference

### 1. `metadata`
| Field | Type | Description |
|---|---|---|
| `tool_name` | `string` | Always `"provikom-converter"`. |
| `tool_version` | `string` | Semantic version of the analyzer (e.g. `"0.1.0"`). |
| `analysis_timestamp` | `string` | ISO 8601 UTC timestamp of the analysis run. |
| `target_file` | `string` | Name of the analyzed archive. |
| `file_size_bytes` | `integer` | File size in bytes. |
| `sha256` | `string` | 64-character hexadecimal SHA-256 hash. |

### 2. `archive_summary`
| Field | Type | Description |
|---|---|---|
| `total_entries` | `integer` | Total entries (files and directories) in the archive. |
| `total_classes` | `integer` | Count of `.class` files. |
| `total_resources` | `integer` | Count of non-class, non-native resource assets. |
| `total_native_libraries` | `integer` | Count of bundled native binaries (`.dll`, `.so`, `.dylib`). |
| `total_nested_archives` | `integer` | Count of embedded JAR/ZIP files. |
| `total_uncompressed_bytes` | `integer` | Cumulative uncompressed size. |
| `total_compressed_bytes` | `integer` | Total size of compressed streams. |
| `resource_breakdown` | `object` | Mapping of file extensions to counts (e.g., `".png": 12`). |
| `security_warnings` | `array[string]` | Security alerts (e.g. zip-bomb ratio or embedded archives). |

### 3. `manifest`
| Field | Type | Description |
|---|---|---|
| `main_class` | `string \| null` | Value of `Main-Class` from `MANIFEST.MF`. |
| `class_path` | `array[string]` | List of referenced classpath entries. |
| `created_by` | `string \| null` | Build tool / JDK info from manifest. |
| `build_jdk` | `string \| null` | Target JDK specification. |
| `raw_attributes` | `object` | Key-value dictionary of all manifest attributes. |

### 4. `class_file_info`
| Field | Type | Description |
|---|---|---|
| `min_major_version` | `integer` | Lowest JVM class major version found (e.g. 52 = Java 8). |
| `max_major_version` | `integer` | Highest JVM class major version found (e.g. 66 = Java 22). |
| `min_java_version` | `string` | Human-readable string (e.g. `"Java 8"`). |
| `max_java_version` | `string` | Human-readable string (e.g. `"Java 22"`). |
| `unique_major_versions` | `array[integer]` | List of all distinct major versions present in classes. |
| `has_native_methods` | `boolean` | `true` if any class contains native method declarations. |

### 5. `features_detected`
Contains categorization of detected capabilities into:
- `gui_frameworks`: Java Swing, Java AWT, JavaFX, Eclipse SWT.
- `audio_apis`: `javax.sound.sampled`, `javax.sound.midi`.
- `threading_apis`: `Thread`, `Runnable`, `java.util.concurrent`.
- `io_apis`: `java.io.File`, `java.nio.file`.
- `network_apis`: `java.net.Socket`, `java.net.URL`.
- `reflection_apis`: `java.lang.reflect`, `sun.misc.Unsafe`.
- `external_libraries`: NetBeans `AbsoluteLayout`, etc.
- `native_features`: JNI calls, native methods.

Each feature contains:
- `name` (`string`)
- `category` (`string`)
- `description` (`string`)
- `severity` (`"info"` | `"warning"` | `"blocker"`)
- `matched_symbols` (`array[string]`)

### 6. `backend_compatibility`
Contains evaluations for `cheerpj`, `teavm`, and `swingjs`.
Each evaluation contains:
- `backend_id` (`string`)
- `backend_name` (`string`)
- `is_open_source` (`boolean`)
- `status` (`"supported"` | `"supported_with_workarounds"` | `"unsupported"` | `"requires_source"` | `"unknown"`)
- `confidence_score` (`float` between 0.0 and 1.0)
- `summary` (`string`)
- `verified_capabilities` (`array[string]`)
- `assumptions_and_risks` (`array[string]`)
- `blockers` (`array[string]`)
- `workarounds_needed` (`array[string]`)
- `remediation_steps` (`array[string]`)

### 7. `recommendation`
- `primary_backend` (`string`)
- `secondary_backend` (`string | null`)
- `feasibility` (`"ready"` | `"workaround_required"` | `"blocked"`)
- `key_takeaways` (`array[string]`)

### 8. `lifecycle` (additive in Milestone 2B)

`lifecycle` separates a **static compatibility prediction** from **execution
evidence**. It is optional in the report schema so reports generated before
Milestone 2B remain valid.

| Field | Type | Description |
|---|---|---|
| `state` | `string` | One of `analyzed`, `candidate`, `built`, `runtime_verified`, `failed`, `unsupported`. |
| `prediction_only` | `boolean` | `true` when no browser execution evidence exists. |
| `execution_verified` | `boolean` | `true` only after automated or manual browser verification passed. |
| `source` | `string` | `static_analysis`, `artifact_generation`, or `browser_verification`. |
| `verification` | `object` | Verification state, automation/manual flags, evidence record, screenshots, console errors. |

#### Lifecycle states

| State | Meaning |
|---|---|
| `analyzed` | Static bytecode/compatibility analysis completed. No artifact exists. |
| `candidate` | Static analysis predicts the archive can be built, but no artifact has been generated. |
| `built` | A static artifact was generated successfully. **This is not runtime verification.** |
| `runtime_verified` | Automated/manual browser checks confirmed rendered UI and expected interactions. |
| `failed` | Browser execution or verification failed (for example, PongGame audio initialization). |
| `unsupported` | The archive cannot be targeted by the selected backend. |

Canvas mounting alone never promotes an artifact to `runtime_verified`. The
static `backend_compatibility` block and artifact `compatibility` block remain
predictions and are not rewritten by verification.

#### Schema migration 2A -> 2B

- The compatibility report schema keeps the same `$id` and required fields.
- `lifecycle` is additive and optional; 2A reports without it still validate.
- Artifact manifests move from schema `1.0` to `1.1` to add `lifecycle`.
- Manifest readers must treat `lifecycle` as optional so 1.0 bundles continue to
  load.
- Runtime evidence is written to `verification.json` next to the artifact and
  referenced from the manifest lifecycle block.

---

## Artifact Manifest Schema

The artifact manifest is separate from the compatibility report. Schema `1.1`
adds `lifecycle` and supports two backend-specific shapes under the same `$id`:

### CheerpJ JAR artifact

Required backend fields include `runtime_version`, `jar_file`,
`java_major_version`, the JAR identity fields under `game`, and the JAR paths
under `paths`.

### SwingJS source artifact

Required backend fields include:

| Field | Meaning |
|---|---|
| `source_project.main_class` | Selected Java entry point. |
| `source_project.source_sha256` | Deterministic hash of all Java source files. |
| `source_project.files` | Relative path and SHA-256 for each source file. |
| `source_project.generated_js` | Generated JavaScript path inside the artifact. |
| `source_project.generated_js_sha256` | Hash of the generated application JavaScript. |
| `runtime` | SwingJS/Java2Script runtime and compiler versions. |
| `toolchain` | Pinned JDK, Eclipse, Java2Script, and runtime hashes. |
| `paths.web_root` / `paths.virtual_mount_root` | Static hosting roots. |
| `ownership` | Artifact ID and ownership marker binding. |

SwingJS source manifests intentionally have no `jar_file` and are not valid
CheerpJ manifests. Artifact readers must branch on `backend`.

`source_project` and `toolchain` are defined in the schema, but additional
diagnostic fields may be present. Unknown fields remain forward-compatible.
