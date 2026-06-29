# Hands-on Lab: k3s p(WSL or macOS)

**You need:** Windows with WSL2 and an Ubuntu distro (run `wsl --install -d Ubuntu` from PowerShell if you don't have one). On macOS, follow the Multipass alternative in Step 0 instead.

**KCNA domains this lab covers:**
- **Kubernetes Fundamentals (44%)** — the cluster, nodes, pods, namespaces, services
- **Cloud Native Application Delivery (16%)** — Helm
- **Cloud Native Architecture (12%)** — observability with Prometheus + Grafana

Run every command in the **Ubuntu** shell unless a step says PowerShell.

---

## Step 0 (Windows / WSL) — turn on systemd

k3s runs as a systemd service, and WSL keeps systemd off by default. Switch it on once.

```bash
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
```

What the lines do:
- `sudo tee /etc/wsl.conf` writes to a root-owned file. `tee` takes whatever you pipe into it and saves it to that path. `>/dev/null` throws away tee's screen echo so it doesn't clutter the terminal.
- `<<'EOF' ... EOF` is a heredoc: everything between the two `EOF` markers becomes the file's content. The quotes around `'EOF'` tell the shell to write the text literally rather than expanding anything inside it.

Restart WSL from **PowerShell** so the setting takes hold:

```powershell
wsl --shutdown
```

Reopen Ubuntu and run `systemctl is-system-running`. Either `running` or `degraded` means systemd is up.

---

## Step 0 (macOS) — get a Linux VM with Multipass


macOS can't run k3s natively because k3s only runs on Linux, so you give it a small Ubuntu VM and run k3s inside that. Install Multipass with `brew install --cask multipass`, then:

```bash
multipass launch --name k3slab --cpus 2 --memory 4G --disk 20G
multipass shell k3slab
```

What the lines do:
- `multipass launch` creates and boots a VM. `--name` labels it; `--cpus`, `--memory`, and `--disk` size it.
- `multipass shell k3slab` drops you into that VM's Ubuntu shell.

You're now in Ubuntu, so skip the Windows Step 0 ( real VM already runs systemd) and start at Step 1. Everything matches except one detail at Step 5, noted there.

If you don't want to install k3s by hand, *Rancher Desktop* packages k3s in a free GUI app and wires up kubectl for you.

---

## Step 1 — install k3s

```bash
curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" sh -
```

What each piece does:
- `curl -sfL https://get.k3s.io` downloads the official install script. `-s` keeps curl quiet, `-f` makes it fail cleanly on an HTTP error, and `-L` follows redirects.
- `| ... sh -` pipes that script straight into `sh` to run it. The trailing `-` tells `sh` to read the script from the pipe.
- `K3S_KUBECONFIG_MODE="644"` is an environment variable the installer reads. It sets the cluster credentials file to permissions `644` — you can read it, so you skip `sudo` on every later command.

The script installs the k3s binary, creates `kubectl` and `crictl` shortcuts, and starts k3s as a service.

---

## Step 2 — point kubectl at the cluster

```bash
mkdir -p ~/.kube
cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
echo 'export KUBECONFIG=$HOME/.kube/config' >> ~/.bashrc
source ~/.bashrc
```

A kubeconfig holds the cluster's address and your credentials; kubectl reads it to know what to talk to. Here you:
- `mkdir -p ~/.kube` creates the standard config folder. `-p` makes parent folders as needed and stays quiet if the folder already exists.
- `cp ...` copies k3s's kubeconfig into that folder under the default name kubectl looks for.
- `echo '...' >> ~/.bashrc` appends one line to your shell startup file. `>>` adds to a file; a single `>` would overwrite it. That line sets `KUBECONFIG` in every new shell.
- `source ~/.bashrc` re-reads that file into the current shell, so the change applies now instead of after you reopen the terminal.

---

## Step 3 — check the cluster

```bash
kubectl get nodes
kubectl get pods -A
```

- `kubectl get nodes` lists the machines in the cluster. You see one node marked `Ready` with the role `control-plane`. On a single node it acts as both brain and worker.
- `kubectl get pods -A` lists pods. `-A` (short for `--all-namespaces`) shows every namespace; without it you'd see only the default one.

You'll spot the pieces k3s ships with: `coredns` (in-cluster DNS), `local-path-provisioner` (local-disk storage), `metrics-server` (basic stats), and `traefik` plus `svclb-traefik` (the bundled ingress and load balancer). `Running` means healthy; one-shot `Completed` install jobs are normal.

---

## Step 4 — install Prometheus + Grafana

Helm is Kubernetes' package manager: it installs a whole stack from one chart instead of making you write dozens of manifests by hand. Install it if it's missing:

```bash
which helm || curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

`which helm` checks whether helm already sits on your PATH. `||` means "if that check failed, run the next command," so helm installs only when it's absent.

Register the chart repository and refresh its index:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

- `helm repo add <alias> <url>` saves the repo under a short local name.
- `helm repo update` pulls the latest list of charts from it.

Write a values file that adjusts the chart for k3s:

```bash
cat > monitoring-values.yaml <<'EOF'
kubeEtcd:
  enabled: false
kubeControllerManager:
  enabled: false
kubeScheduler:
  enabled: false
EOF
```

`cat > monitoring-values.yaml <<'EOF' ... EOF` writes everything between the markers into that file. These three settings switch off scrape targets that don't exist as separate endpoints on k3s — k3s folds etcd, the controller-manager, and the scheduler into one process, so leaving them on just produces permanent "target down" alerts.

**On WSL only, add this block too** (put it before the closing `EOF`). node-exporter tries to mount the host's root filesystem, WSL's root isn't a shared mount, and the runtime rejects it with a `CreateContainerError`. This setting drops that mount:

```yaml
prometheus-node-exporter:
  hostRootFsMount:
    enabled: false
```

You give up root-disk-usage figures but keep CPU, memory, network, and load — fine for a lab. A real VM (Multipass) doesn't need this.

Install the stack:

```bash
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace -f monitoring-values.yaml
kubectl get pods -n monitoring -w
```

- `helm upgrade --install <release> <chart>` installs the chart if it's new and upgrades it if it already exists, so you can re-run it safely.
- `-n monitoring` operates in a namespace called `monitoring` — a labelled partition of the cluster that keeps this stack tidy and easy to remove.
- `--create-namespace` creates that namespace if it isn't there yet.
- `-f monitoring-values.yaml` feeds in your settings file and overrides the chart's defaults.
- `kubectl get pods -n monitoring -w` watches the pods in that namespace. `-w` streams changes live. Press Ctrl-C once everything reads `Running` or `Completed`.

---

## Step 5 — open Grafana

Grafana generates an admin password and stores it as a Secret. Read it back (the username is `admin`):

```bash
kubectl -n monitoring get secret monitoring-grafana -o jsonpath="{.data.admin-password}" | base64 -d ; echo
```

- `kubectl -n monitoring get secret monitoring-grafana` fetches that Secret from the `monitoring` namespace.
- `-o jsonpath="{.data.admin-password}"` prints just the one field you want instead of the whole object.
- `| base64 -d` decodes it. Kubernetes stores Secret values base64-encoded, not encrypted.
- `; echo` prints a newline so the password doesn't run into your next prompt.

Forward Grafana to your machine:

```bash
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
```

`port-forward svc/monitoring-grafana 3000:80` opens a tunnel from your local port `3000` to the service's port `80`. WSL shares localhost with Windows, so open **http://localhost:3000** in your browser and log in. The command holds the terminal open while the tunnel runs — open a second tab for anything else.

**On macOS (Multipass)** the VM doesn't share localhost with the Mac, so bind to all interfaces and use the VM's IP:

```bash
kubectl -n monitoring port-forward --address 0.0.0.0 svc/monitoring-grafana 3000:80
multipass info k3slab
```

`--address 0.0.0.0` listens on every interface, and `multipass info k3slab` shows the VM's IPv4. Open `http://<vm-ip>:3000` from the Mac.

In Grafana, go to **+ → Import**, enter `1860`, click **Load**, and pick the Prometheus datasource. That's the "Node Exporter Full" dashboard — live CPU, memory, and disk.

---

## Step 6 — reset to a clean slate

This is a throwaway cluster, so one script removes k3s and all its data:

```bash
/usr/local/bin/k3s-uninstall.sh
rm -rf ~/.kube
```

`k3s-uninstall.sh` deletes the binary, the service, and the cluster data. `rm -rf ~/.kube` drops your local kubeconfig so nothing stale points at the gone cluster. Ubuntu itself stays untouched. To rebuild, start again at Step 1.

---

## Troubleshooting

- **A pod sits in `ContainerCreating` for a minute** — normal while images pull. Only worry if it stays there.
- **node-exporter loops on `CreateContainerError` with "path / is mounted on / but it is not a shared or slave mount"** — the WSL host-root issue from Step 4. Add the `prometheus-node-exporter.hostRootFsMount.enabled: false` block to your values file and re-run the `helm upgrade`.
- **A pod sticks on `ImagePullBackOff`** — on a corporate network with SSL inspection, image pulls can fail certificate checks. That points at the network, not the lab.
- **kubectl says "permission denied" reading k3s.yaml** — you missed `K3S_KUBECONFIG_MODE="644"` in Step 1. Reinstall with it, or run `sudo chmod 644 /etc/rancher/k3s/k3s.yaml`.
