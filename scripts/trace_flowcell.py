import os
import requests
import json
import sys
import subprocess
import yaml
import argparse
from datetime import datetime

class get_stuff:
    def __init__(self, api_base_url, access_headers, req_verify, tag):
        self.api_base_url = api_base_url
        self.headers = access_headers
        self.verify = req_verify
        self.tag = tag
    
    def get_traces_for_tag(self):
        traces_response = requests.get(
            "{}/{}/?{}={}".format(self.api_base_url, "traces", "trace_tag", self.tag),
            verify = self.verify,
            headers = self.headers)
        if not traces_response.ok:
            raise Exception("Response not OK, got: " + traces_response.text)
        self.traces = json.loads(traces_response.text)
        return json.loads(traces_response.text)
    
    def get_executions_from_traces(self):
        for trace in self.traces:
            trace_id = trace["id"]
            trace_info_response = requests.get(
                "{}/{}/{}".format(self.api_base_url, "traces", trace_id),
                verify = self.verify,
                headers = self.headers)
            trace_info = json.loads(trace_info_response.text)
            action_executions = map(lambda x: x["object_id"], trace_info["action_executions"])
            for execution in action_executions:
                yield execution

    def get_actions_from_executions(self, executions):
        for execution_id in executions:
            execution_info_response = requests.get(
                "{}/{}/{}".format(self.api_base_url, "executions", execution_id),
                verify = self.verify,
                headers = self.headers)
            execution_info = json.loads(execution_info_response.text)
            yield execution_info
    
    def filter_actions_by_name(self, actions, name):
        self.filtered_actions = (action for action in actions if name in action["action"]["name"])

    def sort_actions_by_timestamp(self):
        def get_start_time(action):
            start_time = datetime.strptime(action['start_timestamp'].split(".")[0], "%Y-%m-%dT%H:%M:%S")
            return start_time
        sort_actions = sorted(self.filtered_actions, key = get_start_time)
        return sort_actions


class runfolders:
    def __init__(self):

        with open(args.config, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
        hosts = cfg['runfolder_svc_urls']

        self.hitcount = 0
        self.outstring = "\n\tstatus\trunfolder_link\n"
        for host in hosts:
            url_base = '/'.join(host.split('/')[:-1])
            result = requests.get("{}?state=*".format(url_base))
            result_json = json.loads(result.text)
            self.all_runfolders = result_json["runfolders"]

    def pick_runfolder(self, search_term):
        folders = {}
        states = {}
        choice = 0
        for runfolder in self.all_runfolders:
                link = runfolder["link"]
                state = runfolder["state"]
                if search_term in link and not "rchive" in link and not "biotank" in link:
                    self.hitcount += 1
                    dirs = link.split('/')
                    folders[self.hitcount] = dirs[-1]
                    states[self.hitcount] = state
                    self.outstring += "{}\t{}\t{}\n".format(self.hitcount, state, folders[self.hitcount])
        
        print self.outstring
        
        if self.hitcount == 0:
            print "No hits found, will terminate."
            exit(0)
        elif self.hitcount > 1:
            self.choice = int(raw_input("Which runfolder to trace: "))
        else:
            self.choice = 1
            
        return folders[self.choice], states[self.choice]


def print_stackstorm_output(sorted_actions):
    for a in sorted_actions:
        bashCommand = "st2 execution get {}".format(a["id"])
        process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE) 
        output, error = process.communicate()
        print output
        
def print_stackstorm_id(sorted_actions):
    for a in sorted_actions:
        print a["id"]
        

if __name__ == "__main__":

    # Try to load access token from environment - fall back if not available
    try:
        access_token = os.environ['ST2_AUTH_TOKEN']
    except KeyError as e:
            print("Could not find ST2_AUTH_TOKEN in environment. "
                "Please set it to your st2 authentication token.")
    access_headers = {"X-Auth-Token": access_token}
        
    parser = argparse.ArgumentParser(description="Gets execution ids associated with a flowcell "
                                     "(e.g. a runfolder) and a workflow. It can be used to track "
                                     "executions, e.g: python scripts/trace_flowcell.py "
                                     "--flowcell 000000000-ABGT6_testbio14 ")
    parser.add_argument('--flowcell',     required=True)
    parser.add_argument('--noverify',     action="store_false")
    parser.add_argument('--api_base_url', default="http://localhost:9101/v1")
    parser.add_argument('--config',       default="/opt/stackstorm/packs/snpseq_packs/config.yaml")
    parser.add_argument('--workflow',     default="workflow")
    args = parser.parse_args()

    get_runfolder = runfolders()
    folder2trace, folder_state = get_runfolder.pick_runfolder(args.flowcell)

    print "Will trace {}.".format(folder2trace)

    find = get_stuff(args.api_base_url, access_headers, args.noverify, folder2trace)
    traces = find.get_traces_for_tag()
    executions = find.get_executions_from_traces()
    actions = find.get_actions_from_executions(executions)
    filtered_actions = find.filter_actions_by_name(actions, args.workflow)
    sorted_actions = find.sort_actions_by_timestamp()
    
    try:
        print_stackstorm_output(sorted_actions)
    except OSError as w:
        z = w
        print "\nIt looks as if stackstorm [st2] is unavailable. I will just list the IDs:"
    print_stackstorm_id(sorted_actions)
    
    print "    {} [{}]\n".format(folder2trace, folder_state)
    
    sys.exit()