KubeServiceViewer
# Introduction

KubeServiceViewer is a web application designed to provide real-time visibility into Kubernetes services within your cluster. It displays services across namespaces, including details such as name, type, and access addresses, and integrates with Virtual Services to display routes and protocols.

This tool is particularly useful for QA and development teams who need up-to-date environment configurations as the project evolves.

# Features

- **Comprehensive Service Listing**: View all services across namespaces with filtering options.
- **Virtual Services Integration**: Displays routes and protocols for gateway-proxy services.
- **Cluster Identification**: Easily distinguish between environments with cluster names displayed.
- **User-Friendly Interface**: Modern web UI with filtering options and dark mode.
- **Configurable Settings**: Adjust settings via environment variables.

# Prerequisites

- Kubernetes or OpenShift cluster.
- `kubectl` or `oc` command-line tool configured to interact with your cluster.
- Docker (for building the image).
- Python 3.6+ (if running locally).

# Installation

1. **Clone the Repository**

    ```bash
    git clone https://github.com/bilotto/KubeServiceViewer.git
    cd kube-service-viewer
    ```

2. **Create a Service Account and Obtain a Token**

    To allow the application to interact with the Kubernetes API, you need to create a service account with the appropriate permissions and obtain its token.

    > **Warning**: Assigning the `cluster-admin` role to a service account grants it full permissions on the cluster. This is not recommended for production environments due to security risks. It's advisable to assign the minimal required permissions necessary for the application to function.

    Create Service Account:

    ```bash
    oc create sa admin -n default
    ```

    Add Cluster Role to Service Account:

    ```bash
    oc adm policy add-cluster-role-to-user cluster-admin system:serviceaccount:default:admin
    ```

    Get the Service Account Token:

    ```bash
    # Get the name of the token secret
    TOKEN_SECRET_NAME=$(oc get secrets -n default | grep "admin-token" | awk '{print $1}')

    # Extract the token value
    TOKEN=$(oc get secret $TOKEN_SECRET_NAME -n default -o jsonpath='{.data.token}' | base64 --decode)
    ```

    Alternatively, you can get the token directly:

    ```bash
    TOKEN=$(oc serviceaccounts get-token admin -n default)
    ```

3. **Build the Docker Image**

    ```bash
    docker build -t kube-service-viewer:latest .
    ```

4. **Deploy to Kubernetes/OpenShift**

    Create a Kubernetes Secret to Store the API Token:

    ```bash
    kubectl create secret generic kube-config --from-literal=api_token="$TOKEN"
    ```

    Deploy the Application Using the Provided YAML Files:

    ```bash
    kubectl apply -f deployment.yaml
    kubectl apply -f service.yaml
    ```

5. **Access the Application**

    Determine the application's external IP and port:

    ```bash
    kubectl get service kube-service-viewer
    ```

    Open your web browser and navigate to:

    ```php
    http://<EXTERNAL-IP>:<PORT>/
    ```

# Configuration

The application can be configured using the following environment variables:

- `API_URL`: The URL of the Kubernetes API server (e.g., `https://your-api-server:6443`).
- `API_TOKEN`: The token for accessing the API server (stored in the `kube-config` secret).
- `PORT`: The port on which the application will run inside the container (default is `8080`).
- `INCLUDE_NODEPORT`: Set to 'true' or 'false' to include or exclude NodePort services (default is 'true').

These variables can be set in the `deployment.yaml` file under the `env` section:

```yaml
env:
  - name: API_URL
    value: "https://your-api-server:6443"
  - name: API_TOKEN
    valueFrom:
      secretKeyRef:
        name: kube-config
        key: api_token
  - name: INCLUDE_NODEPORT
    value: "true"
  - name: PORT
    value: "8080"
```

# Security Considerations

- **Service Account Permissions**: It's recommended to create a service account with the minimal permissions required. Instead of `cluster-admin`, consider defining a custom role with the necessary permissions to list services and nodes.
- **API Token Security**: Keep the API token secure. Do not expose it in logs or version control systems.

# Contact

For questions or support, please contact [fbilotto@gmail.com](mailto:fbilotto@gmail.com).
