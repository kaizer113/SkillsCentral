# Deployment and service operations

The app runs in one Docker container on an existing shared Compute Engine VM. Application and Vertex AI model placement stay in GCP `us-east4`. The deployment scripts reuse the VM and the existing Redis/Iris services. A reserved public IP keeps the application URL and Gateway upstream stable across VM shutdowns.

## Private configuration

Create the Python environment described in [the README](../README.md), copy `.env.example` to `.env`, and configure the existing service URLs, IDs, and credentials there. Supply these deployment settings in the same ignored file:

| Variable | Purpose |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | Your GCP project for deployment and Vertex AI. |
| `DEMO_VM_INSTANCE` | Existing shared VM name. |
| `DEMO_VM_ZONE` | Existing zone in `us-east4`; defaults to `us-east4-c`. |
| `DEMO_APP_PORT` | Available, reachable host port; defaults to `8084`. |
| `DEMO_PUBLIC_HOST` | VM hostname or IPv4 address, without scheme or port. Used by the MCP host allowlist. |

Use the signed-in `gcloud` account with access to that VM. The VM's existing service account needs access to the configured Vertex AI model. Ensure the chosen host port is reachable through the existing network configuration. The app listens on container port `8084`, mapped to the configured host port.

The scripts parse configuration without evaluating `.env` as shell code. Actual deployment identifiers, local credentials, diagnostic captures, and the original private brief are excluded from Git.

## Deploy

```bash
bash scripts/deploy.sh
```

The [deployment script](../scripts/deploy.sh) transfers source, fictional fixtures, documentation, requirements, and the private environment to `/opt/skillscentral`, builds the image on the VM, and replaces only the `skillscentral` container. It checks `/api/health` before reporting success. The ignored environment file is mounted read-only and is excluded from the Docker image.

The image and container carry `owner=lionel_giavelli` and `skip_deletion=yes`. Additional supported resources must use those labels and remain in `us-east4`.

## Stop, resume, and inspect

```bash
bash scripts/demo-service.sh status
bash scripts/demo-service.sh stop
bash scripts/demo-service.sh start
bash scripts/demo-service.sh restart
bash scripts/demo-service.sh logs
```

The [service-control script](../scripts/demo-service.sh) addresses only this container. Stopping the shared VM would affect other demos. Stopping the app prevents its model requests; the shared VM and existing Redis/Iris services retain independent billing. Redis records under `SkillsCentral:` and immutable Playbook history persist across app restarts.

## Shut down and restart the VM

When the whole shared VM should be off, use:

```bash
bash scripts/demo-vm.sh stop
bash scripts/demo-vm.sh status
# Later, restore the existing demo without a rebuild:
bash scripts/demo-vm.sh start
```

The [VM-control script](../scripts/demo_vm.py) reads the same private configuration. Before stopping, it checks that the configured public host matches the VM and its existing address is reserved. This prevents shutdown from releasing a temporary address and breaking the demo URL or the Context Gateway upstream. It stops the VM without separately stopping containers, so their restart policies remain effective. **Every service on the shared VM is offline while the VM is stopped.**

Startup resumes the VM and waits for both `/api/health` (including Redis connectivity) and `/api/usage`. Docker must be enabled at boot; the deployed container uses `--restart unless-stopped`. Normal automatic startup needs no SSH connection. If the app does not become healthy, the script tries SSH to start the existing `skillscentral` container, including if someone previously stopped it. The persistent boot disk retains `/opt/skillscentral`, the private configuration, and the local image. Redis history and catalog records remain in the existing Redis Cloud database; Iris services and immutable Playbook versions remain outside this VM. No source sync or demo reset is needed after a normal restart.

The existing public IP has been promoted to a regional static address in `us-east4`, labeled `owner=lionel_giavelli` and `skip_deletion=yes`. [Google documents address promotion](https://docs.cloud.google.com/vpc/docs/reserve-static-external-ip-address#promote_ephemeral_ip): it preserves the address already assigned to the VM. The control script does not create or delete resources. Stopping the VM ends its active compute usage; retained disks, the reserved IP, and existing Redis/Iris services can continue to incur charges. See [Google's stop/start documentation](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance).

Before presenting after a restart, run the Gateway-assisted prompt below. The startup health checks do not exercise Gemini, the remote Gateway, Agent Memory, or Lens end to end.

## Verify the deployment

Open the configured host and port, click **Architecture** to inspect the component map, and check the Integrations view. Then run one fresh agent turn and inspect the steps, session/user IDs, trace ID, loaded skill version, and token counts. Process health alone does not prove that every external service works.

Use the Gateway-assisted jacket prompt in [the runbook](../demo/runbook.md). It should discover a read-only tool, call `skillscentral__get_order`, and calculate the assessment from the active published procedure. All dashboard history comes from actual application activity; fictional data is explicitly labeled.

The MCP endpoint is `/mcp` on the same host and port. Register it as an upstream of the existing Context Gateway using namespace `skillscentral`. A proper protocol check initializes an MCP client, lists all three tools, and calls one with a fictional ID such as `SC-1001`. Browser navigation alone is not a protocol check.

## Regional scope

The application and model use GCP `us-east4`. Existing Iris services may be hosted separately; the original demonstration reuses Iris endpoints in AWS `us-east-1`. This is a cross-cloud demonstration with network access between the components. The [architecture document](architecture.md) shows the boundaries and known Lens reporting limitation.
