# AWS EC2 + Vivado 2026.1 plan for the VCU129 estimate

## What this run will and will not prove

An ordinary x86-64 EC2 virtual machine can run Vivado synthesis, placement,
routing, and timing analysis for the exact VCU129 FPGA part
`xcvu29p-fsga2577-2L-e`. It does not need an FPGA attached. The resulting
`post_route.dcp` is a real physical implementation of the decoder core for that
part, and the post-route reports give mapped resources and timing.

This does **not** physically execute the design on a VCU129. EC2 F1 uses a
different FPGA and platform shell, so it is not a substitute for a VCU129.
Physical execution and a board-final bitstream still require a VCU129 plus the
small self-test wrapper and board constraints described in `PLAN.md`.

The current Tcl flow is out-of-context (OOC). Its routed checkpoint is therefore
the final floorplan of the unchanged decoder **core**, not yet the final
pin-constrained floorplan of an entire VCU129 board design.

## Licensing gate

The permanently free Vivado 2026.1 BASIC tier cannot target Virtex UltraScale+
or Virtex UltraScale+ 58G devices. It therefore cannot target XCVU29P. The
no-license-cost route is AMD's node-locked, full-featured, all-device **60-day
evaluation license**. Treat it as a single evaluation window and do not start it
until the VM and input bundle are ready.

Long-term alternatives are:

1. a paid Vivado CORE or higher license;
2. an AMD University Program/academic Enterprise entitlement; or
3. an applicable VCU129 development-kit voucher.

Current AMD references:

- [Vivado tiers, device matrix, and 60-day evaluation](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado/vivado-licensing-options.html)
- [Generate a node-locked license and choose its Host ID](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Create-and-Generate-a-License-Key-File)
- [Install a certificate-based node-locked license](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Install-Certificate-Based-Node-Locked-License-Key-File)

## Exact VM recommendation

Use this first; it is the lowest-cost current x86-64 option with 64 GiB, which
still leaves defensible headroom over AMD's published XCVU29P peak.

| Setting | Selection |
|---|---|
| Region | `us-east-1` (US East, N. Virginia) |
| Purchase model | On-Demand, not Spot |
| AMI | Canonical Ubuntu Server 22.04 LTS, HVM/SSD, `amd64`/x86-64 |
| AMI publisher owner | Canonical `099720109477` |
| Instance | `r6a.2xlarge`: 8 vCPU, 64 GiB RAM, AMD EPYC x86-64 |
| Root disk | 250 GiB encrypted gp3, 3,000 IOPS / 125 MiB/s initially |
| Access | AWS Systems Manager Session Manager; no inbound ports |
| Network | Public subnet and auto public IPv4 for outbound downloads; no Elastic IP |
| Protection | Require IMDSv2 and enable termination protection |

AMD lists XCVU29P at 28 GB typical and 47 GB peak memory. Sixty-four GiB is the
least-expensive capacity with defensible headroom; 32 GiB is too close to the
published peak for this 1.36-million-line generated design. If the process is
killed for memory, stop the EBS-backed instance, resize to `r6a.4xlarge`
(128 GiB), start it, verify the license Host ID, and resume with a fresh output
directory.

Do not choose a Graviton/ARM instance such as R7g. Vivado 2026.1 supports
x86-64 operating systems. Relevant references:

- [Vivado 2026.1 supported operating systems](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Supported-Operating-Systems)
- [AMD device memory table](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado/vivado-buy.html)
- [AWS R6a sizes](https://aws.amazon.com/ec2/instance-types/r6a/)
- [Official EC2 `us-east-1` price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.json)
- [Find official Canonical AMIs](https://documentation.ubuntu.com/aws/en/latest/aws-how-to/instances/find-ubuntu-images/)

## Stage 1: prepare the AWS account

Direct pages:

- [Create an AWS account](https://signin.aws.amazon.com/signup?request_type=register)
- [Standard On-Demand vCPU quota in `us-east-1`](https://us-east-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-1216C47A?region=us-east-1)
- [Launch an EC2 instance in `us-east-1`](https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#LaunchInstances:)

1. Sign up using the **Paid account plan**, not the Free account plan. The
   required R6a instance is outside the Free-plan instance list. New accounts
   receive the same initial AWS credit on either plan, while Paid permits this
   instance; usage beyond credits is pay-as-you-go. Choose free Basic Support.
2. Enable MFA on the AWS root account and perform normal work through an IAM
   administrator role or IAM Identity Center.
3. Create a small AWS Budget with both actual and forecast email alerts.
4. In **Service Quotas -> Amazon EC2**, check `Running On-Demand Standard
   (A, C, D, H, I, M, R, T, Z) instances`. Request at least 16 vCPUs in the
   chosen region. New accounts can default to five.
5. Create a private S3 staging bucket. Keep **Block Public Access** enabled.
   Use two prefixes, for example `chipsldpc/input/` and `chipsldpc/results/`.
6. Create an EC2 role called `chipsldpc-vivado-ssm`:
   - attach `AmazonSSMManagedInstanceCore`;
   - add only `s3:GetObject`, `s3:PutObject`, and `s3:ListBucket` for the two
     private prefixes above;
   - do not attach `AmazonS3FullAccess`.

Session Manager gives a browser/CLI shell without SSH keys or an inbound port:
[AWS Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html).

## Stage 2: launch the instance

In **EC2 -> Launch instance**:

1. Name it `chipsldpc-vivado-vcu129`.
2. Select the Canonical Ubuntu 22.04 LTS `amd64` image and verify Canonical's
   owner ID. Do not select `arm64`.
3. Select `r6a.2xlarge` and On-Demand capacity.
4. Proceed without a key pair because access will be through Session Manager.
5. Use a public subnet with outbound Internet access. Give the security group
   zero inbound rules. Default outbound access is simplest for this temporary
   host.
6. Create a 250 GiB encrypted gp3 root EBS volume. Keep delete-on-termination
   enabled, but do not terminate until results have been retrieved.
7. Under advanced settings, attach `chipsldpc-vivado-ssm`, require IMDSv2, and
   enable termination protection.
8. Add tags such as `Project=chipsLDPC` and `AutoStop=true`.
9. Launch, wait for both status checks, then choose **Connect -> Session
   Manager**.

Use On-Demand for the first run. A Spot interruption can discard hours of
uncheckpointed placement/routing. A stopped EBS-backed instance retains its
disk and network interface, but EBS storage continues to incur charges:
[AWS stop/start behavior](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html).

## Stage 3: prepare Ubuntu

Run in the Session Manager shell:

```sh
uname -m
lsb_release -ds
free -h
df -h /

sudo apt update
sudo apt upgrade -y
sudo apt install -y build-essential curl git libtinfo5 tmux unzip xz-utils

curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" \
  -o "$HOME/awscliv2.zip"
unzip -q "$HOME/awscliv2.zip" -d "$HOME/awscli-install"
sudo "$HOME/awscli-install/aws/install"
aws --version
```

Expected architecture is `x86_64`; stop if it says `aarch64`. AMD explicitly
notes that Ubuntu needs `libtinfo.so.5`. If the installer later reports other
missing libraries, use AMD's bundled `installLibs.sh` rather than guessing a
large dependency list:
[AMD required-library check](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Checking-Required-Libraries).

## Stage 4: package and upload the exact design

The generated RTL is not safely reproducible from the upstream Git repository
alone because the current chipsLDPC worktree has generated/untracked state.
Transfer the already-verified artifact and the minimal flow.

On the local Mac:

```sh
cd /Users/ashish/Documents/Codex-projects/chipsLDPC

tar -czf /private/tmp/chipsldpc-vcu129-input.tar.gz \
  fpga_bb144_minimal \
  build/generated/static-steane/StaticTannerDatapath.sv \
  build/generated/bivariate-bicycle-144/artifact/rtl/StaticTannerArtifact.sv

shasum -a 256 \
  /private/tmp/chipsldpc-vcu129-input.tar.gz \
  build/generated/bivariate-bicycle-144/artifact/rtl/StaticTannerArtifact.sv
```

The RTL hash must be:

```text
75b24310196ebd66a7e03133bb2a2010be165f395f96fc1e3d125b34262ef300
```

Upload `/private/tmp/chipsldpc-vcu129-input.tar.gz` to the private S3 input
prefix using the S3 console or local AWS CLI. Do not make it public.

On EC2:

```sh
mkdir -p "$HOME/stage" "$HOME/chipsLDPC"
aws s3 cp \
  s3://YOUR_PRIVATE_BUCKET/chipsldpc/input/chipsldpc-vcu129-input.tar.gz \
  "$HOME/stage/chipsldpc-vcu129-input.tar.gz"

tar -xzf "$HOME/stage/chipsldpc-vcu129-input.tar.gz" \
  -C "$HOME/chipsLDPC"

sha256sum \
  "$HOME/chipsLDPC/build/generated/bivariate-bicycle-144/artifact/rtl/StaticTannerArtifact.sv"
```

Stop if the hash differs.

## Stage 5: download and install Vivado 2026.1

Sign in to AMD on the local machine and download the **Linux Self Extracting
Web Installer** for Vivado 2026.1. Upload that approximately 394 MB installer to
the private S3 input prefix. Do not upload or redistribute the 98 GB full image.

- [AMD Vivado 2026.1 downloads](https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2026-1.html)

Copy it to EC2, then extract the headless installer client:

```sh
aws s3 cp \
  s3://YOUR_PRIVATE_BUCKET/chipsldpc/input/FPGAs_AdaptiveSoCs_Unified_2026.1_Lin64.bin \
  "$HOME/stage/FPGAs_AdaptiveSoCs_Unified_2026.1_Lin64.bin"

chmod 700 "$HOME/stage/FPGAs_AdaptiveSoCs_Unified_2026.1_Lin64.bin"

"$HOME/stage/FPGAs_AdaptiveSoCs_Unified_2026.1_Lin64.bin" \
  --keep --noexec --target "$HOME/amd-web-installer"

cd "$HOME/amd-web-installer"
./xsetup -b AuthTokenGen
./xsetup -b ConfigGen
```

The authentication command asks for the AMD account interactively; its token
expires after seven days. Do not put credentials in a script or shell history.

During `ConfigGen`, create `$HOME/install_config.txt`, choose a user-writable
installation path with no spaces (the absolute form of `$HOME/amd`), and select
only:

- Vivado;
- Virtex UltraScale+ / Virtex UltraScale+ 58G device support.

Leave Vitis, Vitis HLS, PetaLinux, Model Composer, and cable drivers unselected.
Generate the configuration with the installed version instead of hand-writing
configuration keys because the menu and keys can change by release.

Install:

```sh
cd "$HOME/amd-web-installer"
./xsetup -b Install \
  -a XilinxEULA,3rdPartyEULA \
  -c "$HOME/install_config.txt"
```

Official batch-flow references:

- [Extract the Web Installer](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Extract-Web-Installer-Batch-Mode-Client)
- [Acquire the seven-day authentication token](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Acquire-Authentication-Token)
- [Generate an install configuration](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Generate-a-Configuration-File)
- [Download and install in batch mode](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Web-Installer-Download-and-Install)

Validate the executable:

```sh
source "$HOME/amd/Vivado/2026.1/settings64.sh"
vivado -version
```

## Stage 6: generate and install the evaluation license

Do this only after the instance and Vivado installation are stable.

1. Source `settings64.sh` and obtain the Ethernet Host ID:

   ```sh
   source "$HOME/amd/Vivado/2026.1/settings64.sh"
   lmutil lmhostid -ether
   ```

2. Save that value outside the VM with the instance ID and primary ENI ID.
3. In AMD Product Licensing, select `Vivado Design Suite 60 Days Evaluation
   License`, generate a **node-locked** license, choose Ethernet/MAC Host ID,
   and enter the 12-hex-digit Host ID from `lmutil`.
4. Download the resulting `Xilinx.lic`, transfer it through the private S3
   prefix, then install it:

   ```sh
   mkdir -p "$HOME/.Xilinx"
   chmod 700 "$HOME/.Xilinx"
   aws s3 cp \
     s3://YOUR_PRIVATE_BUCKET/chipsldpc/input/Xilinx.lic \
     "$HOME/.Xilinx/Xilinx.lic"
   chmod 600 "$HOME/.Xilinx/Xilinx.lic"
   ```

5. Delete the staged license from S3 after confirming it works. Never commit it
   to Git or place it in a public AMI/bucket.

`$HOME/.Xilinx` is an AMD-supported automatic license location. If necessary,
also set:

```sh
export XILINXD_LICENSE_FILE="$HOME/.Xilinx/Xilinx.lic"
```

The license is bound to the selected Host ID. Keep the same EC2 instance and
primary ENI; do not terminate and recreate it during the evaluation. AWS
normally preserves the attached network interface across stop/start, but record
and re-check `lmutil lmhostid -ether` after any stop, start, or resize. If it
changes, use AMD's documented rehost procedure rather than editing the license:
[AMD license rehosting](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Rehost-Change-Node-Locked-or-License-Server-Host-ID-for-a-License-File).

## Stage 7: run the small license/tool smoke test

Run Vivado inside `tmux`; otherwise a lost browser session could terminate the
process.

```sh
tmux new -s vivado

cd "$HOME/chipsLDPC"
source "$HOME/amd/Vivado/2026.1/settings64.sh"
mkdir -p build/fpga-bb144/steane-ooc-01

vivado -mode batch \
  -log build/fpga-bb144/steane-ooc-01/vivado.log \
  -journal build/fpga-bb144/steane-ooc-01/vivado.jou \
  -source fpga_bb144_minimal/run_ooc.tcl -tclargs \
  build/generated/static-steane/StaticTannerDatapath.sv \
  xcvu29p-fsga2577-2L-e 10.000 \
  build/fpga-bb144/steane-ooc-01 StaticTannerDatapath
```

Detach with `Ctrl-b`, then `d`; reattach with `tmux attach -t vivado`.

Acceptance criteria:

- Vivado recognizes `xcvu29p-fsga2577-2L-e`;
- no license-checkout error occurs;
- `run_metadata.txt` ends with `status=PASS`;
- `checkpoints/post_route.dcp` and all reports exist.

The flow rejects stale results. On any rerun, use a fresh directory such as
`steane-ooc-02`.

## Stage 8: run the exact BB144 implementation

After the Steane run passes:

```sh
cd "$HOME/chipsLDPC"
source "$HOME/amd/Vivado/2026.1/settings64.sh"
mkdir -p build/fpga-bb144/vcu129-10ns-ooc-01

vivado -mode batch \
  -log build/fpga-bb144/vcu129-10ns-ooc-01/vivado.log \
  -journal build/fpga-bb144/vcu129-10ns-ooc-01/vivado.jou \
  -source fpga_bb144_minimal/run_ooc.tcl -tclargs \
  build/generated/bivariate-bicycle-144/artifact/rtl/StaticTannerArtifact.sv \
  xcvu29p-fsga2577-2L-e 10.000 \
  build/fpga-bb144/vcu129-10ns-ooc-01 StaticTannerArtifact
```

In a second Session Manager shell, monitor without disturbing the run:

```sh
tail -f "$HOME/chipsLDPC/build/fpga-bb144/vcu129-10ns-ooc-01/vivado.log"
```

Also check `free -h` and `df -h /` periodically. If Linux kills Vivado for
memory, resize to 256 GiB and restart into a new output directory. Do not treat
generic Yosys counts or post-synthesis timing as the final result.

## Stage 9: interpret the result

The essential outputs are:

| Output | Meaning |
|---|---|
| `checkpoints/post_synth.dcp` | mapped netlist before physical implementation |
| `reports/post_synth_util.rpt` | early exact-part mapped resource estimate |
| `checkpoints/post_route.dcp` | authoritative routed OOC core floorplan |
| `reports/post_route_util.rpt` | final implemented LUT/FF/BRAM/URAM/DSP counts |
| `reports/slr_util.rpt` | distribution across VU29P SLRs |
| `reports/route_status.rpt` | fully routed/no route errors check |
| `reports/post_route_timing.rpt` | WNS/TNS, WHS/THS, and critical paths |
| `reports/congestion.rpt` | placement/routing pressure |
| `reports/drc.rpt` | implementation-rule violations |
| `run_metadata.txt` | part, period, Vivado version, route state, slack, status |

`status=PASS` means routed, error-free, and nonnegative setup/hold slack at
10 ns. `status=TIMING_NOT_MET` can still be a valid routed floorplan/resource
result: inspect `routed_fully=1`, `routing_errors=0`, DRC count, WNS, and WHS.
The current script deliberately writes the checkpoint and reports before
returning the timing failure.

If the first route misses 100 MHz, calculate the guarded next period from the
routed critical delay, create a fresh output directory, and rerun. Do not quote
an achieved frequency until both setup and hold pass after route.

## Stage 10: retrieve and optionally inspect the floorplan

Archive all evidence, not just the utilization table:

```sh
cd "$HOME/chipsLDPC"

tar -czf "$HOME/bb144-vcu129-results.tar.gz" \
  -C build/fpga-bb144 vcu129-10ns-ooc-01

sha256sum "$HOME/bb144-vcu129-results.tar.gz"

aws s3 cp "$HOME/bb144-vcu129-results.tar.gz" \
  s3://YOUR_PRIVATE_BUCKET/chipsldpc/results/bb144-vcu129-results.tar.gz
```

Download the archive locally, verify its SHA-256, and retain the RTL hash,
Vivado version, exact part, EC2 type, reports, log, journal, and DCP together.

The reports and DCP are sufficient for the engineering estimate. If a visual
floorplan is needed, install Amazon DCV on the same EC2 instance only after the
batch route succeeds, tunnel port 8443 through Session Manager, and leave the
security group closed. In the Vivado GUI Tcl console:

```tcl
open_checkpoint /home/USER/chipsLDPC/build/fpga-bb144/vcu129-10ns-ooc-01/checkpoints/post_route.dcp
```

Then open **Window -> Device** and inspect the four SLRs, congestion, and
critical paths. DCV is optional and should not block the first estimates:
[Amazon DCV Linux setup](https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-installing-linux-server.html).

## Stage 11: stop and clean up

1. Confirm the result archive can be opened from S3.
2. Stop the instance immediately when it is idle. Compute billing stops, but
   EBS billing continues.
3. Keep the stopped instance only while the node-locked evaluation and follow-up
   runs are needed.
4. When all evidence is safe, disable termination protection, terminate the
   instance, and verify that the 250 GiB volume was deleted.
5. Keep the AMD license private. Do not publish an AMI containing Vivado or the
   license.

`r6a.2xlarge` is not a Free-Tier-eligible instance. New-account credits can
offset its charges, but the account must use the Paid plan to launch it. At the
current `us-east-1` Linux On-Demand rate it is $0.4536/hour; 250 GiB baseline gp3
is $20/month, prorated for the time it exists. Verify the live rate in the
launch summary before choosing **Launch instance**.

## Decision gate after this run

- If BB144 does not fit after synthesis, stop: the unchanged fully parallel
  architecture is too large for VCU129 and needs architectural serialization.
- If it fits but cannot route, use the congestion and per-SLR reports before
  considering pblocks or RTL changes.
- If it routes but misses timing, the DCP is still a real floorplan/resource
  estimate; rerun once at a justified clock period.
- If it routes and meets timing, proceed to the minimal BRAM/ROM self-test
  wrapper and real VCU129 board XDC. That later build, not this OOC run, is the
  bitstream-ready board implementation.
