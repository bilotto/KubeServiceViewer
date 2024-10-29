import threading
import time
import logging
from kubernetes import client
from kubernetes.client import CustomObjectsApi
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from flask import Flask, render_template
from urllib.parse import urlparse


class TimerThread(threading.Thread):
    def __init__(self, interval, function, args=None):
        threading.Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.args = args if args else []
        self.daemon = True

    def run(self):
        while True:
            logger.debug(f"TimerThread executing {self.function.__name__}")
            self.function(*self.args)
            time.sleep(self.interval)

class EventThread(threading.Thread):
    def __init__(self, event, function, args=None):
        threading.Thread.__init__(self)
        self.event = event
        self.function = function
        self.args = args if args else []
        self.daemon = True

    def run(self):
        while True:
            logger.debug("EventThread waiting for event")
            self.event.wait()
            logger.debug(f"EventThread executing {self.function.__name__}")
            self.function(*self.args)
            self.event.clear()

class ParsedService:
    def __init__(self, name, namespace, lb_ip, port, node_port, port_name, prefix, protocol, node_ip):
        self.name = name
        self.namespace = namespace
        self.lb_ip = lb_ip
        self.port = str(port)
        self.node_port = str(node_port)
        self.port_name = port_name
        self.prefix = prefix
        self.protocol = protocol
        self.node_ip = node_ip

    @property
    def url(self):
        # Decide which IP and port to use
        if self.lb_ip:
            ip = self.lb_ip
            port = self.port
        else:
            ip = self.node_ip
            port = self.node_port

        # Determine protocol based on port
        if port == "443":
            protocol = 'https'
            port_part = ''
        elif port == "80":
            protocol = 'http'
            port_part = ''
        elif self.port == "80":
            protocol = 'http'
            port_part = f":{port}"
        elif self.port == "443":
            protocol = 'https'
            port_part = f":{port}"
        else:
            protocol = self.protocol.lower()
            port_part = f":{port}"

        # Build the URL
        prefix = self.prefix or ''
        return f"{protocol}://{ip}{port_part}{prefix}"


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class KubeServiceViewerApp:

    def __init__(self, api_url, api_token):
        self.app = Flask(__name__)
        self.api_url = api_url
        self.api_token = api_token
        self.include_nodeport = os.environ.get('INCLUDE_NODEPORT', 'true').lower() == 'true'
        self.configure_kube_client()
        self.custom_api = CustomObjectsApi(self.kube_client.api_client)
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.nodes = self.kube_client.list_node()
        self.setup_routes()
        self.start_threads()
        self.all_services = dict()
        self.parsed_services = dict()
        self.global_dict = dict()

    @property
    def cluster_name(self):
        parsed_url = urlparse(self.api_url)
        return parsed_url.hostname or 'Unknown Cluster'


    @property
    def node_ip(self):
        return self.nodes.items[0].status.addresses[0].address if self.nodes.items else ''

    def run(self):
        port = int(os.environ.get('PORT', 8080))
        self.app.run(host='0.0.0.0', port=port)

    def configure_kube_client(self):
        if not self.api_url.startswith('https://'):
            self.api_url = 'https://' + self.api_url.lstrip('http://').lstrip('https://')
        configuration = client.Configuration()
        configuration.host = self.api_url
        configuration.verify_ssl = False
        configuration.debug = False
        configuration.api_key = {"authorization": "Bearer " + self.api_token}
        self.kube_client = client.CoreV1Api(client.ApiClient(configuration))
        logger.debug(f"Configured Kubernetes client with API URL: {self.api_url}")

    def setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template('index.html', global_dict=self.global_dict)

    def start_threads(self):
        event_thread = EventThread(event=self.event, function=self.parse_services)
        event_thread.start()

        timer_thread = TimerThread(interval=60, function=self.list_services)
        timer_thread.start()

    def list_services(self):
        all_services = self.kube_client.list_service_for_all_namespaces(watch=False)
        self.all_services = all_services.to_dict()
        self.event.set()

    def get_virtual_services(self, namespace):
        group = 'gateway.solo.io'
        version = 'v1'
        plural = 'virtualservices'

        try:
            virtual_services = self.custom_api.list_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural
            )
            return virtual_services.get('items', [])
        except Exception as e:
            logger.exception(f"Error fetching Virtual Services in namespace {namespace}")
            return []

    def parse_services(self):
        parsed_services = []
        namespaces_names = []
        for item in self.all_services.get('items', []):
            try:
                namespace = item.get('metadata', {}).get('namespace')
                service_name = item.get('metadata', {}).get('name')
                service_type = item.get('spec', {}).get('type')
                ports = item.get('spec', {}).get('ports', [])
                lb_ip = ''
                node_ip = self.node_ip

                if service_type == "LoadBalancer":
                    ingress = item.get('status', {}).get('load_balancer', {}).get('ingress', [])
                    if ingress:
                        lb_ip = ingress[0].get('ip', '') or ingress[0].get('hostname', '')
                    else:
                        lb_ip = ''
                elif service_type == "NodePort":
                    if not self.include_nodeport:
                        continue  # Skip NodePort services if not included
                else:
                    continue  # Skip other service types if not LoadBalancer or NodePort

                if namespace not in namespaces_names:
                    namespaces_names.append(namespace)


                if ports:
                    for port in ports:
                        port_name = port.get("name", "")
                        protocol = port.get("protocol", "")
                        port_number = port.get("port")
                        node_port_number = port.get("node_port")

                        if protocol == "TCP":
                            if service_name != "gateway-proxy":
                                service_obj = ParsedService(
                                    name=service_name,
                                    namespace=namespace,
                                    lb_ip=lb_ip,
                                    port=port_number,
                                    node_port=node_port_number,
                                    port_name=port_name,
                                    prefix="",
                                    protocol=protocol,
                                    node_ip=node_ip
                                )
                                parsed_services.append(service_obj)
                        else:
                            logger.info(f"Skipping service {service_name} with protocol {protocol}")

                # Handle Virtual Services for 'gateway-proxy'
                if service_name == "gateway-proxy":
                    virtual_services = self.get_virtual_services(namespace)
                    for vs in virtual_services:
                        vs_name = vs.get('metadata', {}).get('name')
                        vs_spec = vs.get('spec', {})
                        virtual_hosts = vs_spec.get('virtualHost', {})
                        routes = virtual_hosts.get('routes', [])
                        for route in routes:
                            matchers = route.get('matchers', [])
                            for matcher in matchers:
                                prefix = matcher.get('prefix', '')
                                # Determine protocol
                                protocol = 'https' if 'https' in vs_name else 'http'
                                # Use appropriate port
                                for port in ports:
                                    port_name = port.get("name", "")
                                    if port_name != protocol:
                                        continue
                                    port_number = port.get("port")
                                    node_port_number = port.get("node_port")
                                    service_obj = ParsedService(
                                        name=vs_name,
                                        namespace=namespace,
                                        lb_ip=lb_ip,
                                        port=port_number,
                                        node_port=node_port_number,
                                        port_name=port_name,
                                        prefix=prefix,
                                        protocol=protocol,
                                        node_ip=node_ip
                                    )
                                    parsed_services.append(service_obj)
            except Exception as e:
                logger.exception(f"Error processing service: {item}")

        with self.lock:
            self.global_dict['cluster_name'] = self.cluster_name
            self.global_dict['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            self.global_dict['services'] = parsed_services
            self.global_dict['namespaces_names'] = namespaces_names
            self.parsed_services = parsed_services

if __name__ == "__main__":

    api_url = os.environ.get('API_URL')
    api_token = os.environ.get('API_TOKEN')
    app = KubeServiceViewerApp(api_url, api_token)
    app.run()
