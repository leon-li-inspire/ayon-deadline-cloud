# Design Document: AYON Deadline Cloud Integration

## Overview

This design describes the integration between AYON (a VFX/animation pipeline management tool) and AWS Deadline Cloud for render farm submission. The integration follows the approach hooking AYON into the Deadline Cloud Submitter tool rather than creating job bundles directly. AYON handles pipeline concerns (validation, settings pre-population, post-render publishing) while delegating actual job submission to the native Deadline Cloud Submitter.

The addon is structured as a standard AYON server addon with a client-side component. The server side manages settings and configuration (farm profiles, DCC-specific defaults, submission parameters). The client side runs inside DCC applications (Maya, Houdini, etc.) and integrates with the AYON Publisher workflow — collecting render data, running validations, pre-populating the Deadline Cloud Submitter, and handling post-render publishing (version registration, transcoding, validation).

The key architectural principle is **separation of responsibilities**: AYON owns the pipeline (what to render, how to validate, what to do after render), while Deadline Cloud owns the execution (scheduling, resource management, job lifecycle). The integration point is the Deadline Cloud Submitter's hook/callback system, where AYON injects its pipeline logic at well-defined stages.

## MVP Scope

### In Scope (MVP)

- **Studio-configurable validations**: Pre-submission validation plugins that run before any resource-intensive operations. Includes both built-in technical validations (renderable camera exists, valid frame range) and studio-defined custom validations (required AOVs, render settings checks).
- **Publishing and processing results**: Version registration in AYON, transcoding, reviewable creation, burnins, file movement/renaming via path templates.
- **Basic job dependencies**: Render → Post-render (publish) dependency chain.

### Deferred (Post-MVP)

- **Advanced project tracking**: Higher-level job dependencies beyond render→publish, priority management across assets, planning integration, task status updates.
- **Asset-level dependencies**: Complex dependency graphs like "create render archives → render images → publish".
- **Cross-job orchestration**: Managing priorities and dependencies across multiple submissions.

## Architecture

```mermaid
graph TD
    subgraph "DCC Application (Maya/Houdini/etc.)"
        A[AYON Publisher UI] --> B[Collect Plugins]
        B --> C[Validate Plugins]
        C --> D[Deadline Cloud Submitter Bridge]
    end

    subgraph "AYON Server"
        E[Deadline Cloud Addon - Server] --> F[Settings / Farm Profiles]
        F --> G[DCC-Specific Defaults]
    end

    subgraph "Storage Layer"
        S1[Job Attachments - S3 Bucket]
        S2[Shared Storage - Storage Profiles]
    end

    subgraph "AWS Deadline Cloud"
        D --> H[Deadline Cloud Submitter Tool]
        H -->|OJD Job Bundle| I[Deadline Cloud API]
        I --> J[Render Jobs]
        J --> K[Post-Render Job]
        I -.->|CreateMonitor| MON[Job Monitor API]
    end

    subgraph "Post-Render Pipeline"
        K --> L[AYON Post-Render Script]
        L --> M[Output Validation]
        M --> N[Transcoding / Burnins]
        N --> O[Version Registration in AYON]
    end

    A -.->|fetch settings| E
    D -.->|pre-populate options| H
    J -->|read inputs| S1
    J -->|read inputs| S2
    J -->|write outputs| S1
    J -->|write outputs| S2
    L -->|access outputs| S1
    L -->|access outputs| S2
    L -.->|register versions| E
```

## Sequence Diagrams

### Main Submission Flow

```mermaid
sequenceDiagram
    participant Artist
    participant Publisher as AYON Publisher
    participant Collector as Collect Plugins
    participant Validator as Validate Plugins
    participant Bridge as Submitter Bridge
    participant Settings as AYON Server Settings
    participant Submitter as DC Submitter Tool
    participant DC as Deadline Cloud API

    Artist->>Publisher: Open Publisher, select render instances
    Publisher->>Settings: Fetch farm profiles & DCC defaults
    Settings-->>Publisher: DeadlineCloudSettings
    Publisher->>Collector: Run collection plugins
    Collector-->>Publisher: RenderInstance[] (layers, AOVs, cameras)
    Publisher->>Validator: Run validation plugins
    Validator-->>Publisher: Validation results (pass/fail)

    alt Validation Failed
        Publisher-->>Artist: Show validation errors
    else Validation Passed
        Publisher->>Bridge: Submit via Deadline Cloud
        Bridge->>Bridge: Map AYON instances to Submitter params
        Bridge->>Submitter: Pre-populate settings & invoke submission
        Submitter->>DC: CreateJob (render job)
        DC-->>Submitter: job_id
        Submitter->>DC: CreateJob (post-render job, depends on render)
        DC-->>Submitter: post_job_id
        Submitter-->>Bridge: Submission result (job IDs)
        Bridge-->>Publisher: Submission complete
        Publisher-->>Artist: Show success with job IDs
    end
```

### Post-Render Publishing Flow

```mermaid
sequenceDiagram
    participant DC as Deadline Cloud
    participant Script as Post-Render Script
    participant AYON as AYON Server API

    DC->>Script: Trigger post-render job (render complete)
    Script->>Script: Discover rendered output files
    Script->>Script: Validate outputs (frame completeness, file integrity)

    alt Validation Failed
        Script->>DC: Report failure
    else Validation Passed
        Script->>Script: Move/rename files via path templates
        Script->>Script: Run transcoding (if configured)
        Script->>Script: Apply burnins (if configured)
        Script->>AYON: Register version (files, metadata)
        AYON-->>Script: Version registered
        Script->>DC: Report success
    end
```

## Storage and Data Transfer

AWS Deadline Cloud provides two options for managing input and output data:

### Option 1: Job Attachments

Deadline Cloud transfers data to and from Cloud Workers using S3 buckets:
- **Input sync**: Scene files and assets are uploaded to S3 and synced to workers when the job starts
- **Output sync**: Rendered outputs are synced back to the workstation when the job finishes
- **Linux VFS mount**: On Linux workers, job attachments can be mounted as a virtual filesystem for standard file access
- **Output retrieval**: The Deadline CLI provides commands to download job outputs, which can be run manually or as a scheduled CRON job

### Option 2: Shared Storage (Storage Profiles)

Uses storage profiles to remap paths between different filesystems and platforms:
- **Path remapping**: Automatically translates paths between Windows, Linux, and macOS workers
- **Existing files**: Files already on shared storage are not re-uploaded
- **Local files**: Files not on shared storage are uploaded to the job attachments S3 bucket
- **Cross-platform support**: Enables mixed-platform render farms with consistent path resolution

### Post-Render Script Access

The post-render script accesses rendered outputs via:
1. **Job attachments**: Download outputs using Deadline CLI before processing
2. **Shared storage**: Direct filesystem access using remapped paths from storage profiles
3. **Hybrid**: Combination based on storage configuration

### Storage Configuration

The `StorageConfig` in farm profiles determines which storage method is used and how paths are resolved. See the `StorageConfig` data model below.

## Components and Interfaces

### Component 1: Server Settings (`server/settings.py`)

**Purpose**: Define all configurable settings for the addon — farm profiles, DCC defaults, submission parameters, and post-render options. Served to client via AYON server API.

```python
class FarmProfile(BaseSettingsModel):
    """A named farm configuration profile."""
    name: str
    farm_id: str
    queue_id: str
    storage_profile_id: str | None = None
    storage_config: StorageConfig = StorageConfig(storage_mode="job_attachments")
    priority: int = 50
    max_retries: int = 3

class DCCSubmissionDefaults(BaseSettingsModel):
    """Per-DCC default submission parameters."""
    dcc_name: str  # "maya", "houdini", etc.
    job_template: str | None = None
    parameter_overrides: dict[str, Any] = {}

class PostRenderSettings(BaseSettingsModel):
    """Configuration for post-render processing."""
    enable_transcoding: bool = False
    transcode_profiles: list[TranscodeProfile] = []
    burnin_config: BurninConfig = BurninConfig()
    validate_frame_completeness: bool = True
    validate_file_integrity: bool = True

class DeadlineCloudSettings(BaseSettingsModel):
    """Root settings model for the addon."""
    farm_profiles: list[FarmProfile] = []
    default_profile: str = ""
    dcc_defaults: list[DCCSubmissionDefaults] = []
    post_render: PostRenderSettings = PostRenderSettings()
    custom_validations: list[CustomValidation] = []
    auto_detect_credentials: bool = True

class CustomValidation(BaseSettingsModel):
    """Studio-configurable validation rule."""
    name: str
    enabled: bool = True
    dcc_scope: list[str] = []  # Empty = all DCCs, or ["maya", "houdini"]
    validation_type: str       # "required_aovs", "render_settings", "custom_script"
    parameters: dict[str, Any] = {}
    error_message: str = ""
```

**Responsibilities**:
- Store farm connection details (farm ID, queue ID, storage profiles)
- Define per-DCC submission defaults and job template overrides
- Configure post-render pipeline behavior (transcoding, validation)
- Provide sensible defaults for all settings

### Component 2: Render Instance Collector (`client/plugins/collect_render.py`)

**Purpose**: Collect render-related data from the DCC scene — render layers, AOVs, cameras, frame ranges — and package them as AYON instances for the publish pipeline.

```python
class CollectedRenderInstance:
    """Data collected from a DCC scene for a single render unit."""
    instance_name: str
    render_layer: str
    aovs: list[str]
    cameras: list[str]
    frame_range: tuple[int, int]
    frame_step: int
    scene_file: str
    output_dir: str
    expected_files: list[str]
    dcc_specific_data: dict[str, Any]
```

**Responsibilities**:
- Query DCC scene for renderable items (layers, ROPs, write nodes)
- Resolve output paths using AYON anatomy templates
- Calculate expected output file lists for post-render validation
- Package DCC-specific data needed by the submitter

### Component 3: Submitter Bridge (`client/plugins/submit_to_deadline_cloud.py`)

**Purpose**: Bridge between AYON's publish pipeline and the Deadline Cloud Submitter tool. Maps AYON render instances to Submitter parameters, pre-populates settings, and invokes submission. The Submitter collects scene data, presents them in its UI, and creates an Open Job Description (OJD) job bundle — a grouped OJD template with asset references, parameter values, and additional files needed by the job. The job bundle is then submitted via the Deadline Cloud Python API.

```python
class SubmitterBridge:
    """Bridges AYON publish data to Deadline Cloud Submitter."""

    def map_instance_to_params(
        self,
        instance: CollectedRenderInstance,
        settings: DeadlineCloudSettings,
    ) -> SubmissionParams: ...

    def pre_populate_submitter(
        self,
        submitter: Any,  # DC Submitter tool handle
        params: SubmissionParams,
    ) -> None: ...

    def submit(
        self,
        instances: list[CollectedRenderInstance],
        settings: DeadlineCloudSettings,
    ) -> SubmissionResult: ...
```

**Responsibilities**:
- Translate AYON render instances into Deadline Cloud Submitter parameters
- Pre-populate the Submitter with AYON settings before submission
- Attach post-render job configuration to the submission
- Return job IDs and status back to the AYON publish pipeline
- Support job progress monitoring via the Deadline Cloud API (`CreateMonitor`)

### Component 4: Validation Plugins (`client/plugins/validate_*.py`)

**Purpose**: Run AYON-specific validations on collected render data before submission. These run within the AYON Publisher pipeline, before the Submitter is invoked. Validations are critical for farm rendering (especially cloud) to prevent wasting resources on jobs that would fail.

**Validation Categories**:
- **Technical validations** (built-in): Renderable camera exists, valid output paths, scene file integrity
- **Project-context validations** (built-in): Frame range matches AYON context, correct folder/task assignment
- **Studio-configurable validations** (custom): Required render elements/AOVs present, specific render settings enforced, naming conventions, resolution checks — defined per-studio via settings

```python
class ValidateFrameRange:
    """Ensure frame range is valid and matches AYON context."""
    def process(self, instance: CollectedRenderInstance) -> None: ...

class ValidateOutputPaths:
    """Ensure output paths are resolvable and writable."""
    def process(self, instance: CollectedRenderInstance) -> None: ...

class ValidateSceneIntegrity:
    """DCC-specific scene checks before farm submission."""
    def process(self, instance: CollectedRenderInstance) -> None: ...

class ValidateRenderElements:
    """Studio-configurable: Check required AOVs/render elements are present."""
    def process(self, instance: CollectedRenderInstance) -> None: ...

class ValidateRenderSettings:
    """Studio-configurable: Enforce specific render settings (resolution, sampling, etc.)."""
    def process(self, instance: CollectedRenderInstance) -> None: ...
```

**Responsibilities**:
- Validate frame ranges match AYON asset context
- Verify output paths are resolvable via anatomy templates
- Run DCC-specific scene integrity checks
- Execute studio-defined custom validations from settings
- Block submission if any validation fails (with actionable error messages)

### Component 5: Post-Render Script (`client/scripts/post_render.py`)

**Purpose**: Runs as a Deadline Cloud job after rendering completes. Handles output validation, transcoding, burnin application, and version registration in AYON.

**Publishing Process**:
Publishing is the process where a version is registered in AYON. Beyond registration, various operations run during publishing:
- **File movement/renaming**: Locally produced data is moved and renamed to final destinations controlled by AYON path templates (anatomy)
- **Remote data integration**: Data produced outside (e.g., cloud renders) can be directly integrated to final destinations from their online locations, or first downloaded then processed
- **Transcoding**: Convert formats (e.g., EXR → JPEG for review)
- **Burnin application**: Add frame numbers, shot info, and other metadata overlays to review media
- **Additional validations**: Post-render checks on output quality and completeness

```python
class PostRenderProcessor:
    """Handles post-render pipeline on the farm."""

    def discover_outputs(
        self, expected_files: list[str]
    ) -> list[str]: ...

    def validate_outputs(
        self, discovered: list[str], expected: list[str]
    ) -> ValidationResult: ...

    def transcode(
        self, files: list[str], profile: TranscodeProfile
    ) -> list[str]: ...

    def apply_burnins(
        self, files: list[str], burnin_config: BurninConfig
    ) -> list[str]: ...

    def move_to_final_destination(
        self, files: list[str], anatomy_templates: dict
    ) -> list[str]: ...

    def register_version(
        self, files: list[str], metadata: dict[str, Any]
    ) -> str: ...
```

**Responsibilities**:
- Discover and validate rendered output files (frame completeness, file integrity)
- Move/rename files to final destinations using AYON anatomy path templates
- Run transcoding if configured (e.g., EXR → JPEG for review)
- Apply burnins to review media (frame numbers, shot info, custom text)
- Register the rendered version in AYON (files, representations, metadata)
- Report success/failure back to Deadline Cloud

## Data Models

### SubmissionParams

```python
@dataclass
class SubmissionParams:
    """Parameters mapped from AYON instance to DC Submitter format."""
    job_name: str
    farm_id: str
    queue_id: str
    priority: int
    frame_range: str          # "1-100" format for DC
    scene_file: str
    output_dir: str
    job_template: str | None  # OJD template name
    job_bundle_dir: str | None  # Path to assembled OJD job bundle
    parameter_values: dict[str, Any]  # Parameter values for the OJD template
    storage_profile_id: str | None
    storage_config: StorageConfig | None
    max_retries: int
    post_render_config: PostRenderConfig
```

**Validation Rules**:
- `job_name` must be non-empty and contain only alphanumeric, dash, underscore
- `farm_id` and `queue_id` must be valid AWS resource identifiers
- `priority` must be between 0 and 100
- `frame_range` must match pattern `\d+(-\d+)?`
- `scene_file` must be an existing file path
- `post_render_config` must be present

### PostRenderConfig

```python
@dataclass
class PostRenderConfig:
    """Configuration passed to the post-render job."""
    ayon_project: str
    ayon_folder_path: str
    ayon_task: str
    ayon_product_name: str
    expected_files: list[str]
    representations: list[RepresentationConfig]
    transcode_profiles: list[TranscodeProfile]
    burnin_config: BurninConfig
    anatomy_templates: dict[str, str]  # Path templates for file movement/renaming
    storage_config: StorageConfig      # How to access rendered outputs
    ayon_server_url: str
    # Credentials handled via Deadline Cloud's secret management
```

**Validation Rules**:
- `ayon_project`, `ayon_folder_path`, `ayon_task` must be non-empty
- `expected_files` must contain at least one entry
- `representations` must contain at least one entry
- `ayon_server_url` must be a valid URL

### SubmissionResult

```python
@dataclass
class SubmissionResult:
    """Result returned after submitting to Deadline Cloud."""
    success: bool
    render_job_id: str | None
    post_render_job_id: str | None
    error_message: str | None = None
    submitted_instances: list[str] = field(default_factory=list)
```

### TranscodeProfile

```python
@dataclass
class TranscodeProfile:
    """Defines a transcoding operation for post-render."""
    name: str
    input_extension: str       # e.g., ".exr"
    output_extension: str      # e.g., ".jpg"
    ffmpeg_args: list[str]     # Additional ffmpeg arguments
    create_representation: bool = True
```

### StorageConfig

```python
@dataclass
class StorageConfig:
    """Configuration for storage and data transfer."""
    storage_mode: str          # "job_attachments", "shared_storage", or "hybrid"
    storage_profile_id: str | None = None
    s3_bucket_name: str | None = None
    
    # Path mappings for cross-platform support
    path_mappings: list[PathMapping] = field(default_factory=list)
    
    # Job attachments settings
    auto_sync_inputs: bool = True
    auto_sync_outputs: bool = True
    use_vfs_on_linux: bool = False
    
    # Output retrieval settings
    output_download_method: str = "manual"  # "manual", "cron", "on_complete"
    cron_schedule: str | None = None        # e.g., "*/15 * * * *"

@dataclass
class PathMapping:
    """Maps paths between platforms for shared storage."""
    name: str
    windows_path: str | None = None
    linux_path: str | None = None
    macos_path: str | None = None
```

**Validation Rules**:
- `storage_mode` must be one of: "job_attachments", "shared_storage", "hybrid"
- If `storage_mode` is "shared_storage" or "hybrid", `storage_profile_id` must be set
- If `storage_mode` is "job_attachments" or "hybrid", `s3_bucket_name` should be set (or use default)
- `path_mappings` must have at least two platform paths defined per mapping
- `output_download_method` must be one of: "manual", "cron", "on_complete"
- If `output_download_method` is "cron", `cron_schedule` must be a valid cron expression

### BurninConfig

```python
@dataclass
class BurninConfig:
    """Configuration for burnin overlays on review media."""
    enabled: bool = False
    frame_number: bool = True
    shot_name: bool = True
    task_name: bool = False
    custom_text: str | None = None
    font_size: int = 24
    position: str = "bottom"   # "top", "bottom", "both"
```


## Key Functions with Formal Specifications

### Function 1: `SubmitterBridge.map_instance_to_params()`

```python
def map_instance_to_params(
    self,
    instance: CollectedRenderInstance,
    settings: DeadlineCloudSettings,
) -> SubmissionParams:
    """Map an AYON render instance to Deadline Cloud submission parameters.

    Resolves the farm profile, applies DCC-specific defaults, and builds
    the complete parameter set for the Submitter tool.
    """
```

**Preconditions:**
- `instance` is a fully collected render instance (all fields populated)
- `instance.frame_range[0] <= instance.frame_range[1]`
- `settings.farm_profiles` contains at least one profile
- `settings.default_profile` references a valid profile name, or the first profile is used

**Postconditions:**
- Returns a valid `SubmissionParams` with all required fields populated
- `result.farm_id` and `result.queue_id` come from the resolved farm profile
- `result.frame_range` is formatted as DC-compatible string (e.g., "1-100")
- `result.post_render_config` contains all data needed for post-render publishing
- No side effects on `instance` or `settings`

**Loop Invariants:** N/A

### Function 2: `SubmitterBridge.submit()`

```python
def submit(
    self,
    instances: list[CollectedRenderInstance],
    settings: DeadlineCloudSettings,
) -> SubmissionResult:
    """Submit render instances to Deadline Cloud via the Submitter tool.

    Maps each instance to submission params, pre-populates the Submitter,
    and invokes submission. Creates both render and post-render jobs.
    """
```

**Preconditions:**
- `instances` is non-empty
- All instances have passed AYON validation
- `settings` contains valid farm profile configuration
- Deadline Cloud Submitter tool is available and authenticated

**Postconditions:**
- If successful: `result.success is True`, `result.render_job_id` and `result.post_render_job_id` are valid job IDs
- If failed: `result.success is False`, `result.error_message` describes the failure
- Post-render job has a dependency on the render job (runs only after render completes)
- `result.submitted_instances` lists all instance names that were submitted
- No partial submissions: either all instances submit or none do

**Loop Invariants:**
- For each processed instance: the instance has been mapped to valid `SubmissionParams`

### Function 3: `PostRenderProcessor.validate_outputs()`

```python
def validate_outputs(
    self,
    discovered: list[str],
    expected: list[str],
) -> ValidationResult:
    """Validate that rendered outputs match expectations.

    Checks frame completeness (all expected files exist) and
    file integrity (files are non-zero size and readable).
    """
```

**Preconditions:**
- `expected` is non-empty (at least one expected output file)
- `discovered` contains absolute file paths
- `expected` contains absolute file paths

**Postconditions:**
- `result.is_valid` is True if and only if all expected files are present in discovered and all pass integrity checks
- `result.missing_files` contains expected files not found in discovered
- `result.corrupt_files` contains files that exist but fail integrity checks
- No file system modifications

**Loop Invariants:**
- After checking file `i`: `missing_files ∪ valid_files ∪ corrupt_files` accounts for all files checked so far

### Function 4: `PostRenderProcessor.register_version()`

```python
def register_version(
    self,
    files: list[str],
    metadata: dict[str, Any],
) -> str:
    """Register a new version in AYON with the rendered files.

    Creates representations for each file type and attaches
    metadata (frame range, render stats, etc.) to the version.
    """
```

**Preconditions:**
- `files` is non-empty and all files exist on disk
- `metadata` contains required keys: `project`, `folder_path`, `task`, `product_name`
- AYON server is reachable and authenticated

**Postconditions:**
- Returns the version ID of the newly created version
- All files are registered as representations on the version
- Metadata is attached to the version entity
- Version is visible in AYON UI after registration

**Loop Invariants:** N/A

## Algorithmic Pseudocode

### Main Submission Algorithm

```python
def execute_submission(publisher_context, settings):
    """
    ALGORITHM: Main AYON-to-Deadline-Cloud submission workflow.
    INPUT: publisher_context (collected AYON publish context), settings (addon settings)
    OUTPUT: SubmissionResult

    This runs as the "extract" phase of the AYON publish pipeline.
    """

    # Step 1: Resolve farm profile
    profile = resolve_farm_profile(settings)
    assert profile is not None, "No valid farm profile found"

    # Step 2: Collect all render instances from publisher context
    instances = [
        inst for inst in publisher_context.instances
        if inst.data.get("family") == "render"
    ]
    assert len(instances) > 0, "No render instances to submit"

    # Step 3: Map each instance to submission parameters
    all_params = []
    for instance in instances:
        params = map_instance_to_params(instance, settings, profile)
        assert params.farm_id != "" and params.queue_id != ""
        all_params.append((instance, params))

    # Step 4: Pre-populate and invoke Deadline Cloud Submitter
    submitter = get_deadline_cloud_submitter()
    results = []

    for instance, params in all_params:
        # Pre-populate submitter with AYON-derived settings
        pre_populate_submitter(submitter, params)

        # Submit render job
        render_job_id = submitter.submit_job(params)

        # Submit post-render job with dependency on render job
        post_config = build_post_render_config(instance, settings)
        post_job_id = submitter.submit_post_job(
            post_config, depends_on=render_job_id
        )

        results.append(SubmissionResult(
            success=True,
            render_job_id=render_job_id,
            post_render_job_id=post_job_id,
            submitted_instances=[instance.instance_name],
        ))

    # Step 5: Aggregate results
    return aggregate_results(results)
```

### Post-Render Processing Algorithm

```python
def execute_post_render(config: PostRenderConfig, settings: PostRenderSettings):
    """
    ALGORITHM: Post-render processing on the farm.
    INPUT: config (PostRenderConfig from submission), settings (PostRenderSettings)
    OUTPUT: success (bool)

    Runs as a Deadline Cloud job after rendering completes.
    """

    # Step 1: Discover rendered output files
    discovered = discover_output_files(config.expected_files)

    # Step 2: Validate outputs
    validation = validate_outputs(discovered, config.expected_files)

    if not validation.is_valid:
        report_failure(
            f"Missing: {validation.missing_files}, "
            f"Corrupt: {validation.corrupt_files}"
        )
        return False

    # Step 3: Move files to final destinations via path templates
    final_files = move_to_final_destination(
        discovered, config.anatomy_templates
    )

    # Step 4: Transcode if configured
    all_files = list(final_files)
    for profile in config.transcode_profiles:
        matching = [f for f in final_files if f.endswith(profile.input_extension)]
        if matching:
            transcoded = transcode_files(matching, profile)
            all_files.extend(transcoded)

    # Step 5: Apply burnins to review media if configured
    if settings.burnin_config.enabled:
        review_files = [f for f in all_files if is_review_format(f)]
        if review_files:
            burnin_files = apply_burnins(review_files, settings.burnin_config)
            all_files.extend(burnin_files)

    # Step 6: Build representations
    representations = build_representations(all_files, config.representations)

    # Step 7: Register version in AYON
    metadata = {
        "project": config.ayon_project,
        "folder_path": config.ayon_folder_path,
        "task": config.ayon_task,
        "product_name": config.ayon_product_name,
    }
    version_id = register_version(representations, metadata)

    assert version_id is not None, "Version registration failed"
    return True
```

### Farm Profile Resolution Algorithm

```python
def resolve_farm_profile(
    settings: DeadlineCloudSettings,
    override_name: str | None = None,
) -> FarmProfile:
    """
    ALGORITHM: Resolve which farm profile to use for submission.
    INPUT: settings (addon settings), override_name (optional explicit profile)
    OUTPUT: FarmProfile

    Priority: explicit override > instance-level setting > default profile > first profile
    """

    profiles_by_name = {p.name: p for p in settings.farm_profiles}
    assert len(profiles_by_name) > 0, "No farm profiles configured"

    # Check explicit override first
    if override_name and override_name in profiles_by_name:
        return profiles_by_name[override_name]

    # Fall back to default profile
    if settings.default_profile and settings.default_profile in profiles_by_name:
        return profiles_by_name[settings.default_profile]

    # Last resort: first profile
    return settings.farm_profiles[0]
```

## Example Usage

```python
# Example 1: Server settings configuration (in AYON UI)
settings = DeadlineCloudSettings(
    farm_profiles=[
        FarmProfile(
            name="production",
            farm_id="farm-abc123",
            queue_id="queue-xyz789",
            storage_profile_id="sp-def456",
            priority=50,
            max_retries=3,
        ),
        FarmProfile(
            name="previs",
            farm_id="farm-abc123",
            queue_id="queue-previs",
            priority=30,
        ),
    ],
    default_profile="production",
    dcc_defaults=[
        DCCSubmissionDefaults(
            dcc_name="maya",
            job_template="maya-arnold-render",
            parameter_overrides={"renderer": "arnold"},
        ),
    ],
    post_render=PostRenderSettings(
        enable_transcoding=True,
        transcode_profiles=[
            TranscodeProfile(
                name="review",
                input_extension=".exr",
                output_extension=".jpg",
                ffmpeg_args=["-q:v", "2"],
            ),
        ],
    ),
)

# Example 2: Submission from AYON Publisher (client-side plugin)
bridge = SubmitterBridge()
result = bridge.submit(
    instances=collected_render_instances,
    settings=addon_settings,
)
if result.success:
    print(f"Render job: {result.render_job_id}")
    print(f"Post-render job: {result.post_render_job_id}")
else:
    print(f"Submission failed: {result.error_message}")

# Example 3: Post-render script execution (on farm worker)
processor = PostRenderProcessor()
outputs = processor.discover_outputs(config.expected_files)
validation = processor.validate_outputs(outputs, config.expected_files)
if validation.is_valid:
    processor.transcode(outputs, transcode_profile)
    version_id = processor.register_version(outputs, metadata)
```

## Correctness Properties

The following properties must hold for the integration to be correct:

1. **Submission Atomicity**: For any set of render instances submitted together, either all instances are submitted successfully (all job IDs returned) or none are (rollback on partial failure).

2. **Settings Propagation**: For all settings `s` configured in AYON server and all submissions using those settings, the Deadline Cloud Submitter receives parameters consistent with `s` — i.e., `submitter.farm_id == resolved_profile(s).farm_id`.

3. **Validation Gate**: For all render instances `i`, if any validation plugin reports failure on `i`, then `i` is never submitted to Deadline Cloud. Formally: `∀i: validation_failed(i) ⟹ ¬submitted(i)`.

4. **Post-Render Ordering**: For all post-render jobs `p` with dependency on render job `r`, `p` executes only after `r` completes successfully. Formally: `∀(r, p): depends_on(p, r) ⟹ completed(r) before started(p)`.

5. **Frame Completeness**: For all post-render validations, the set of discovered files must be a superset of expected files for the validation to pass. Formally: `∀v: v.is_valid ⟹ expected_files ⊆ discovered_files`.

6. **Version Registration Idempotency**: Registering the same version with the same files and metadata multiple times produces exactly one version in AYON (handles retries gracefully).

7. **Profile Resolution Determinism**: For the same settings and override inputs, `resolve_farm_profile` always returns the same profile. The resolution order is deterministic: explicit override > default > first.

## Error Handling

### Error Scenario 1: Deadline Cloud Submitter Not Available

**Condition**: The Deadline Cloud Submitter tool/library is not installed or not importable in the DCC environment.
**Response**: Fail early during plugin discovery with a clear error message: "AWS Deadline Cloud Submitter is not installed. Please install the deadline-cloud-for-{dcc} package."
**Recovery**: User installs the required submitter package and retries.

### Error Scenario 2: Authentication Failure

**Condition**: AWS credentials are not configured or expired when attempting submission.
**Response**: Catch authentication errors from the Submitter and surface them in the AYON Publisher UI with guidance on credential configuration.
**Recovery**: User configures AWS credentials (via `aws configure`, environment variables, or Deadline Cloud Monitor) and retries.

### Error Scenario 3: Partial Render Failure (Missing Frames)

**Condition**: Render job completes but some frames are missing or corrupt.
**Response**: Post-render validation detects missing/corrupt files, reports the specific frames affected, and marks the Deadline Cloud job as failed.
**Recovery**: Artist can re-submit only the failed frames (if supported) or re-submit the entire job. The post-render job does not register a partial version.

### Error Scenario 4: AYON Server Unreachable During Post-Render

**Condition**: Post-render script cannot reach the AYON server to register the version.
**Response**: Retry with exponential backoff (3 attempts, 5s/15s/45s delays). If all retries fail, mark the Deadline Cloud job as failed with the connection error.
**Recovery**: Once AYON server is back, the post-render job can be manually retried from the Deadline Cloud console.

### Error Scenario 5: Invalid Farm Profile Configuration

**Condition**: Settings reference a farm ID or queue ID that doesn't exist in Deadline Cloud.
**Response**: The Submitter returns an error on submission. The bridge catches this and reports it in the Publisher UI with the specific invalid resource ID.
**Recovery**: Admin corrects the farm profile settings in AYON server.

## Job Monitoring

Job progress can be monitored via the Deadline Cloud API using `CreateMonitor`. This enables:
- Real-time progress tracking of render jobs from within AYON
- Notification when jobs complete, fail, or require attention
- Integration with AYON's event system for automated status updates

For MVP, monitoring is informational only — artists can check job status via the Deadline Cloud Monitor UI or the AYON Publisher. Deeper integration (automatic retries, AYON task status updates) is deferred to post-MVP.

## Testing Strategy

### Unit Testing Approach

- Test `map_instance_to_params` with various instance configurations and settings combinations
- Test `resolve_farm_profile` with all priority paths (override, default, fallback)
- Test validation plugins independently with mock DCC data
- Test `PostRenderProcessor.validate_outputs` with complete, partial, and empty file sets
- Test `PostRenderConfig` serialization/deserialization (data must survive round-trip through Deadline Cloud job parameters)
- Coverage goal: 90%+ on bridge logic and validation plugins

### Property-Based Testing Approach

**Property Test Library**: `hypothesis` (Python)

- **Profile resolution determinism**: For any valid settings, calling `resolve_farm_profile` twice with the same inputs returns the same result
- **Frame range mapping**: For any valid `(start, end)` tuple where `start <= end`, the mapped DC frame range string parses back to the same range
- **Submission params completeness**: For any valid `CollectedRenderInstance` and `DeadlineCloudSettings`, `map_instance_to_params` returns params where all required fields are non-empty
- **Validation correctness**: For any file list where `expected ⊆ discovered`, validation returns `is_valid=True`; for any list where `expected ⊄ discovered`, returns `is_valid=False`

### Integration Testing Approach

- End-to-end submission test with mocked Deadline Cloud API (using `moto` or similar)
- Test the full Publisher pipeline: collect → validate → submit → verify job creation
- Test post-render script with fixture files simulating rendered outputs
- Test AYON version registration with a test AYON server instance
- DCC-specific integration tests for Maya and Houdini collectors (requires DCC licenses in CI or mock DCC APIs)

## Performance Considerations

- **Batch submission**: When submitting multiple render layers, batch API calls to Deadline Cloud where possible rather than one-at-a-time
- **File discovery**: For large frame ranges (1000+ frames), use parallel file existence checks in post-render validation
- **Settings caching**: Cache resolved farm profiles and DCC defaults for the duration of a publish session (settings don't change mid-publish)
- **Transcoding parallelism**: Run transcoding operations in parallel across frames using worker threads, bounded by available CPU cores

## Security Considerations

- **AWS Credentials**: Never store AWS credentials in AYON settings. Rely on Deadline Cloud's native credential management (Deadline Cloud Monitor, IAM roles, environment variables)
- **AYON API Token for Post-Render**: The post-render script needs AYON server access. Use Deadline Cloud's secret management to pass the AYON API token to the job, never embed it in job parameters
- **Scene File Access**: Ensure farm workers have read access to scene files and write access to output directories via Deadline Cloud storage profiles
- **Input Sanitization**: Validate all user-provided strings (job names, paths) before passing to the Submitter to prevent injection

## Dependencies

- **AYON Server** (>= 1.0.7): Server-side addon hosting and settings API
- **AYON Launcher**: Client-side plugin execution environment
- **AWS Deadline Cloud Submitter** (`deadline-cloud-for-maya`, `deadline-cloud-for-houdini`, etc.): Native DCC submitter tools that handle actual job creation
- **`deadline` Python package**: AWS Deadline Cloud client library for API interactions
- **`ayon-python-api`**: AYON server API client (used in post-render script for version registration)
- **`ffmpeg`** (optional): Required on farm workers if transcoding is enabled
- **DCC Applications**: Maya, Houdini (and potentially others) with their respective AYON integrations installed
