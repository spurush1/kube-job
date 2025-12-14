# 🛠️ Setup Guide: Local Development Environment

This guide covers how to set up your machine (Mac or Windows) to run the KubeJob Fabric platform.

## 📋 Prerequisites
You need the following tools installed:
1.  **Docker Desktop** (Container Runtime)
2.  **Minikube** (Local Kubernetes Cluster)
3.  **Kubectl** (Kubernetes CLI)
4.  **Python 3.9+** (For scripts & backend dev)
5.  **Node.js 18+** (For Dashboard frontend)

---

## 🍎 macOS Setup

The easiest way is using **Homebrew**. If you don't have it, install it from [brew.sh](https://brew.sh).

### 1. Install Docker
Download and install **Docker Desktop for Mac**:
[https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
*   Start Docker Desktop and wait for the engine to be running.

### 2. Install Tools via Brew
Open your terminal and run:
```bash
brew install minikube kubectl python node
```

### 3. Start Minikube
```bash
minikube start --driver=docker --memory=4096 --cpus=2
```

### 4. Verify
```bash
kubectl get nodes
# Should show "minikube   Ready   control-plane"
```

---

## 🪟 Windows Setup

We strongly recommend using **WSL2 (Windows Subsystem for Linux)** for the best compatibility with the bash scripts.

### 1. Install WSL2
Open PowerShell as Administrator:
```powershell
wsl --install
```
*   Restart your computer if prompted.
*   This installs **Ubuntu** by default. Open the "Ubuntu" app to set up your username/password.

### 2. Install Docker Desktop
Download and install: [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
*   **Important**: In Docker Settings > General, ensure "Use the WSL 2 based engine" is CHECKED.
*   In Docker Settings > Resources > WSL Integration, enable integration for your Ubuntu distro.

### 3. Install Tools (Inside WSL Ubuntu)
Open your **Ubuntu** terminal (not PowerShell) and run:

```bash
# Update
sudo apt-get update && sudo apt-get install -y curl

# Install Minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Install Kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Install Python & Node
sudo apt-get install -y python3 python3-pip nodejs npm
```

### 4. Start Minikube (Inside WSL)
```bash
minikube start --driver=docker
```

---

## 🚀 Running the Project

Once setup is complete, navigate to the project folder and run:

```bash
# 1. Start everything
./platform/manage.sh up

# 2. Forward ports (Keep this terminal open)
./platform/manage.sh forward
```

*   **Dashboard**: `http://localhost:9090`
*   **API**: `http://localhost:8000` (via forward)
*   **Credentials**: `admin` / `password`

See `RUNBOOK.txt` for detailed usage instructions.
