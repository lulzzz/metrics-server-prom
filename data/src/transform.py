# -*- coding: utf-8 -*-
'''
Auther:  cytopia
License: MIT

Transformer for kubernetes-incubator/metrics-server from json
into Prometheus readable format.
'''

import json
import requests
from flask import Flask
from flask import Response


'''
Globals that specify at which url metrics for nodes and pods can be found
'''
PROXY = 'http://127.0.0.1:8080'
URL_NODES = PROXY + '/apis/metrics.k8s.io/v1beta1/nodes'
URL_PODS = PROXY + '/apis/metrics.k8s.io/v1beta1/pods'


def json2dict(data):
    '''
    Safely convert a potential JSON string into a dict

    Args:
        data (str): Valid or invalid JSON string.
    Returns:
        dict: Returns dict of string or empty dict in case of invalid JSON input.
    '''
    json_object = dict()
    try:
        json_object = json.loads(data)
    except ValueError:
        pass
    return json_object


def trans_node_metrics(string):
    '''
    Transforms metrics-server node metrics (in the form of a JSON string) into Prometheus
    readable metrics format (text-based).
    https://prometheus.io/docs/instrumenting/exposition_formats/
    https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form

    Args:
        string (str): Valid or invalid JSON string.
    Returns:
        str: Returns newline separated node metrics ready for Prometheus to pull.
    '''
    data = json2dict(string)
    cpu = []
    mem = []

    cpu.append('# HELP kube_metrics_server_node_cpu The CPU time of a node.')
    cpu.append('# TYPE kube_metrics_server_node_cpu gauge')
    mem.append('# HELP kube_metrics_server_node_mem The memory of a node.')
    mem.append('# TYPE kube_metrics_server_node_mem gauge')

    tpl = 'kube_metrics_server_node_{}{{node="{}",created="{}",timestamp="{}",window="{}"}} {}'

    for node in data.get('items', []):
        lbl = {
            'node': node.get('metadata', []).get('name', ''),
            'created': node.get('metadata', []).get('created', ''),
            'timestamp': node.get('timestamp', ''),
            'window': node.get('window', '')
        }
        val = {
            'cpu': node.get('usage', []).get('cpu', ''),
            'mem': node.get('usage', []).get('memory', '')
        }
        cpu.append(tpl.format('cpu', lbl['node'], lbl['created'], lbl['timestamp'], lbl['window'], val['cpu']))
        mem.append(tpl.format('mem', lbl['node'], lbl['created'], lbl['timestamp'], lbl['window'], val['mem']))
    return '\n'.join(cpu + mem)


def trans_pod_metrics(string):
    '''
    Transforms metrics-server pod metrics (in the form of a JSON string) into Prometheus
    readable metrics format (text-based).
    https://prometheus.io/docs/instrumenting/exposition_formats/
    https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form

    Args:
        string (str): Valid or invalid JSON string.
    Returns:
        str: Returns newline separated node metrics ready for Prometheus to pull.
    '''
    data = json2dict(string)
    cpu = []
    mem = []

    cpu.append('# HELP kube_metrics_server_pod_cpu The CPU time of a pod.')
    cpu.append('# TYPE kube_metrics_server_pod_cpu gauge')
    mem.append('# HELP kube_metrics_server_pod_mem The memory of a pod.')
    mem.append('# TYPE kube_metrics_server_pod_mem gauge')

    tpl = 'kube_metrics_server_pod_{}{{pod="{}",container="{}",namespace="{}",created="{}",timestamp="{}",window="{}"}} {}'

    for pod in data.get('items', []):
        lbl = {
            'pod': pod.get('metadata', []).get('name', ''),
            'ns': pod.get('metadata', []).get('namespace', ''),
            'created': pod.get('metadata', []).get('created', ''),
            'timestamp': pod.get('timestamp', ''),
            'window': pod.get('window', '')
        }
        # Loop over defined container in each pod
        for container in pod.get('containers', []):
            lbl['cont'] = container.get('name', '')
            val = {
                'cpu': container.get('usage', []).get('cpu', ''),
                'mem': container.get('usage', []).get('memory', '')
            }
            cpu.append(tpl.format('cpu', lbl['pod'], lbl['cont'], lbl['ns'], lbl['created'], lbl['timestamp'], lbl['window'], val['cpu']))
            mem.append(tpl.format('mem', lbl['pod'], lbl['cont'], lbl['ns'], lbl['created'], lbl['timestamp'], lbl['window'], val['mem']))
    return '\n'.join(cpu + mem)


application = Flask(__name__) # pylint: disable=invalid-name

@application.route("/metrics")
def metrics():
    '''
    This function is the /metrics http entrypoint and will itself do two callbacks
    to the running kubectl proxy in order to gather node and pod metrics from specified
    kubernetes api urls. Current output is JSON and we must therefore transform both results
    into Prometheus readable format:
        https://prometheus.io/docs/instrumenting/exposition_formats/
        https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form
    '''
    req = {
        'nodes': requests.get(URL_NODES),
        'pods': requests.get(URL_PODS)
    }
    json = {
        'nodes': req['nodes'].text,
        'pods': req['pods'].text
    }
    prom = {
        'nodes': trans_node_metrics(json['nodes']),
        'pods': trans_pod_metrics(json['pods'])
    }
    return Response(prom['nodes'] + '\n' + prom['pods'], status=200, mimetype='text/plain')


@application.route("/healthz")
def healthz():
    '''
    This function is the /healthz http entrypoint and will itself do two callbacks
    in order to determine the health of node and pod metric endpoints.

    Returns:
        Response: Flask Response object that will handle returning http header and body.
                  If one of the pages (nodes or pods metrics by metrics-server) fails,
                  it will report an overall failure and respond with 503 (service unavailable).
                  If both a good, it will respond with 200.
    '''
    req = {
        'nodes': requests.get(URL_NODES),
        'pods': requests.get(URL_PODS)
    }
    health = 'ok'
    status = 200
    if req['nodes'].status_code != 200:
        health = 'failed'
        status = 503
    if req['pods'].status_code != 200:
        health = 'failed'
        status = 503

    return Response(health, status=status, mimetype='text/plain')


@application.route("/")
def index():
    '''
    This function is the / http entrypoint and will simply provide a link to
    the metrics and health page. This is done, because all metrics endpoints I have encountered
    so far also do it exactly this way.

    Returns:
        Response: Flask Response object that will handle returning http header and body.
                  Returns default Prometheus endpoint index page (http 200) with links
                  to /healthz and /metrics.
    '''
    return '''
        <html>
        <head><title>metrics-server-prom</title></head>
        <body>
            <h1>metrics-server-prom</h1>
	    <ul>
                <li><a href='/metrics'>metrics</a></li>
                <li><a href='/healthz'>healthz</a></li>
	    </ul>
        </body>
        </html>
    '''

if __name__ == "__main__":
    application.run(host='0.0.0.0')
