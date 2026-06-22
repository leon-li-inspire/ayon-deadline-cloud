# Building Conda Packages for AYON on Deadline Cloud

## Overview

The AYON publish step on Deadline Cloud SMF workers requires the AYON Launcher. We package the pre-built launcher release as a conda package and host it in an S3 channel that your queue can access.

We package the **AYON Launcher** (cx_Freeze'd binary, ~259 MB) which provides the Python runtime, CLI, and bootstrap logic. The studio's bundle (addons + dependency package) is delivered separately via job attachments per the [June 9 alignment](https://github.com/ynput/ayon-deadline-cloud/discussions/26).

**Steps:**

1.  Install build tools (`pixi`, `rattler-build`).
2.  Write the recipe.
3.  Build the package.
4.  Publish to S3 channel.
5.  Configure queue permissions.
6.  Add the channel to the queue environment.
7.  Test on SMF worker.

---

## Step 1: Install Prerequisites

=== "Linux"
    ```bash
    # Install pixi (package manager)
    curl -fsSL https://pixi.sh/install.sh | bash

    # Install rattler-build (conda package builder)
    pixi global install rattler-build

    # Install rattler-index (channel indexing)
    pixi global install rattler-index
    ```

=== "Windows"
    ```powershell
    # Install pixi (package manager)
    powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"

    # Install rattler-build (conda package builder)
    pixi global install rattler-build

    # Install rattler-index (channel indexing)
    pixi global install rattler-index
    ```

---

## Step 2: Recipe

Directory structure:
```
ayon-conda-recipe/
└── ayon-launcher/recipe/recipe.yaml
```

### ayon-launcher/recipe/recipe.yaml

The recipe can be obtained [here](https://github.com/aws-deadline/deadline-cloud-samples/tree/mainline/conda_recipes/ayon-launcher).

### Key design decisions

- **Platform-specific (linux-64)**: The launcher includes cx_Freeze'd Python 3.11 and compiled extensions. Must be built targeting `--target-platform linux-64`.
- **No runtime conda dependencies**: The launcher is fully self-contained — it bundles its own Python, libraries, and dependencies.
- **`shim/` directory required**: The launcher reads `shim/shim.json` during startup. Omitting it causes `FileNotFoundError`.
- **Activation script**: Sets `AYON_LAUNCHER_DIR` and `AYON_HEADLESS_MODE=1` so the launcher runs headlessly.
- **Symlink to `bin/`**: Makes `ayon` available on PATH in the conda environment.
- **Bundle delivered separately**: The studio's bundle (addons + dependency package) ships via job attachments, not baked into this package. This decouples launcher releases from addon updates.

---

## Step 3: Build


=== "Linux"
    ```bash
    export PATH="$HOME/.pixi/bin:$PATH"
    cd ~/Workspace/deadline-cloud/ayon-conda-recipe

    # Build for linux-64 (cross-build from macOS is fine for binary repackaging)
    rattler-build build -r ayon-launcher/recipe/recipe.yaml --target-platform linux-64
    ```

    Output: `output/linux-64/ayon-launcher-1.6.1-hb0f4dca_1.conda` (~259 MB)

=== "Windows"
    ```powershell
    $env:PATH="$env:HOME\.pixi\bin;$PATH"
    cd ~\Workspace\deadline-cloud\ayon-conda-recipe

    # Build for linux-64 (cross-build from macOS is fine for binary repackaging)
    rattler-build build -r ayon-launcher/recipe/recipe.yaml --target-platform linux-64
    ```

    Output: `output/linux-64/ayon-launcher-1.6.1-hb0f4dca_1.conda` (~259 MB)

---

## Step 4: Publish to S3

```bash
# Upload the package
aws s3 cp output/linux-64/ayon-launcher-1.6.1-hb0f4dca_1.conda \
    s3://lizyang-ayon-conda-channel/Conda/Default/linux-64/

# Index the channel (generates repodata.json)
rattler-index s3 s3://foo-ayon-conda-channel/Conda/Default
```

Verify:
```bash
aws s3 ls s3://foo-ayon-conda-channel/Conda/Default/linux-64/
```

---

## Step 5: Configure Queue Permissions

The queue role needs read access to the S3 bucket hosting the conda channel:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:ListBucket"],
            "Resource": [
                "arn:aws:s3:::foo-ayon-conda-channel",
                "arn:aws:s3:::foo-ayon-conda-channel/*"
            ]
        }
    ]
}
```

Add as inline policy `CondaChannelAccess` on the queue role.

---

## Step 6: Add Channel to Queue Environment

1. Open the Deadline Cloud console → your queue → Environments tab
2. Select the **Conda** queue environment → Edit
3. Find the `CondaChannels` parameter definition
4. Change the default:

```
default: "conda-forge s3://lizyang-ayon-conda-channel/Conda/Default deadline-cloud"
```

Note: `conda-forge` is required by other packages (like DCC adaptors) that depend on `python`.

---

## Step 7: Test on SMF Worker

Submit a test job:

```yaml
specificationVersion: jobtemplate-2023-09
name: Test AYON Launcher
parameterDefinitions:
  - name: CondaPackages
    type: STRING
    default: "ayon-launcher"
steps:
  - name: test-ayon
    script:
      embeddedFiles:
        - name: testScript
          filename: test_ayon.sh
          type: TEXT
          data: |
            #!/bin/bash
            set -x
            which ayon
            ls $CONDA_PREFIX/opt/ayon-launcher/
            ayon --headless --version 2>&1 || true
            echo "Test complete"
      actions:
        onRun:
          command: bash
          args:
            - "{{Task.File.testScript}}"
```

Expected output: launcher starts, reports "AYON Server URL is not set" (expected without credentials), confirming the binary executes correctly.

---

## Troubleshooting

### "ayon-launcher cannot be installed because there are no viable options"

- The channel only has `linux-64/` packages. Check `aws s3 ls s3://.../linux-64/`
- Verify repodata exists: `aws s3 cp s3://.../linux-64/repodata.json -`

### "failed to load repodata"

- The queue role doesn't have S3 access to the bucket
- Ensure the bucket is in the **same account** as the Deadline Cloud farm

### "FileNotFoundError: shim/shim.json"

- The `shim/` directory was not included in the package build
- Verify the recipe copies `shim` in the script section

### "AYON Server URL is not set"

- Expected when running without credentials
- The publish step must set `AYON_SERVER_URL` and `AYON_API_KEY` environment variables (handled by the job attachment hook in Part 2)

### Reindexing a channel

```bash
rattler-index s3 s3://foo-ayon-conda-channel/Conda/Default
```

### Listing packages

```bash
aws s3 ls s3://foo-ayon-conda-channel/Conda/Default/linux-64/
```
