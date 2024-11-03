#!/bin/python3
from bgph_vm import BGPHVirtualMachine
from results import Result, Test
from utils import all_unique
from pathlib import Path
import time
import random
import re
import hashlib
import shutil

class BGPHGrader:
    def __init__(self, vm: BGPHVirtualMachine) -> None:
        self.script_path = Path(__file__).parent
        self.BGPH_path = Path("/autograder/submission/BGPHijacking")
        self.anti_cheating_secret = hashlib.sha256(f"CS6250{time.time()}666".encode()).hexdigest()[0:16]

        self.vm = vm
        ssh_client = self.vm.init()
        if not ssh_client:
            print("Failed to connect to the VM")
            exit(1)

        # open the shells
        self.topology_interactive_shell = ssh_client.invoke_shell()
        self.ssh_client = ssh_client

        self.tests = {
            "report": Test("Report", max_score=5),
            "sanity": Test("Sanity and configuration test", max_score=10),
            "topology": Test("Topology, links, connectivity, BGP", max_score=30),
            "default_website": Test("Default website test", max_score=40),
            "rouge_website": Test("Rogue website test (easy)", max_score=40),
            "default_website_after": Test("Default website after rogue", max_score=5),
            "rouge_hard": Test("Rogue website test (hard)", max_score=20),
        }

        self.anti_hardcode_msg = "Mismatch, please ensure connectivity and topology correctness, and don't modify webserver.py"

    def _prepare_scripts_and_folder(self):
        # copy scripts to submission folder
        scripts = ["scripts/webserver.py", "scripts/start_rogue_hard.sh"]
        for script in scripts:
            shutil.copy(self.script_path / script, self.BGPH_path)

        # ensure logs exists
        (self.BGPH_path / "logs").mkdir(exist_ok=True)

    def _test_report(self):
        test = self.tests["report"]
        test.set_to_max_score()
        success = True
        required_files = ["fig2_topo.pdf"]
        for file in required_files:
            if not (self.BGPH_path / file).exists():
                test.add_error(-5, f"Missing report file: {file}, -5 Points")
                success = False

        test.set_passed(success)
        if success:
            test.add_feedback("Report detected! Please note that we might still manually deduct points of this part if it's not legible")
        return success

    def _test_sanity(self):
        test = self.tests["sanity"]
        test.set_to_max_score()
        success = True

        required_files = ["bgp.py", "connect.sh", "run.py", "start_rogue.sh", "stop_rogue.sh",
                          "webserver.py", "website.sh"]
        required_configs = ["conf/bgpd-R1.conf", "conf/bgpd-R2.conf", "conf/bgpd-R3.conf",
                            "conf/bgpd-R4.conf", "conf/bgpd-R5.conf", "conf/bgpd-R6.conf",
                            "conf/zebra-R1.conf", "conf/zebra-R2.conf", "conf/zebra-R3.conf",
                            "conf/zebra-R4.conf", "conf/zebra-R5.conf", "conf/zebra-R6.conf",
                            ]

        # check each file exists
        for file in required_files:
            if not (self.BGPH_path / file).exists():
                success = False
                test.add_error(-test.max_score, f"Missing required file: {file}, please check your folder structure")
                return success

        # check each config exists
        for file in required_configs:
            if not (self.BGPH_path / file).exists():
                success = False
                test.add_error(-test.max_score, f"Missing required file: {file}, please check your folder structure")
                return success

        # check the configuration files
        if not all_unique(self.BGPH_path, "conf/bgpd-*.conf"):
            test.add_error(-5, "Two or more bgpd conf files are identical, -5 Points")
            success = False

        test.set_passed(success)
        return success

    def _test_topology(self):
        test = self.tests["topology"]
        test.set_to_max_score()
        success = True

        # test switches
        test.add_feedback("Checking required switches present")
        log = self.vm.get_topology_start_output()
        matched_switches = re.findall(r"\*\*\* Adding switches:.*\n(.*?)\n", log)
        switches = set(matched_switches[0].split())
        expected_switches = set(["R1", "R2", "R3", "R4", "R5", "R6"])
        diff = expected_switches - switches
        if diff:
            test.add_error(-5, f"Missing essential switches: {diff}, -5 Points")
            success = False

        # test links
        test.add_feedback("Checking required links present")
        matched_links = re.findall(r"\*\*\* Adding links:.*\n(.*?)\n", log)
        link_pairs = re.findall(r"\((.*?), (.*?)\)", matched_links[0])
        link_pairs = set([frozenset(pair) for pair in link_pairs])
        expected_link_pairs = set([ frozenset({"R1", "R2"}), frozenset({"R1", "R3"}), frozenset({"R1", "h1-1"}),
            frozenset({"R1", "h1-2"}), frozenset({"R2", "R3"}), frozenset({"R2", "R4"}), frozenset({"R2", "R5"}),
            frozenset({"R2", "h2-1"}), frozenset({"R2", "h2-2"}), frozenset({"R3", "R4"}), frozenset({"R3", "R5"}),
            frozenset({"R3", "h3-1"}), frozenset({"R3", "h3-2"}), frozenset({"R4", "R5"}), frozenset({"R4", "h4-1"}),
            frozenset({"R4", "h4-2"}), frozenset({"R5", "R6"}), frozenset({"R5", "h5-1"}), frozenset({"R5", "h5-2"}),
            frozenset({"R6", "h6-1"}), frozenset({"R6", "h6-2"}),])
        diff = expected_link_pairs - link_pairs
        if diff:
            msg = "Missing essential links: "
            for pair in diff:
                msg += f"{tuple(pair)}, "
            msg += ", -5 Points"
            test.add_error(-5, msg)
            success = False

        available_routers = ["R1", "R2", "R3", "R4", "R5"]
        random_router = random.choice(available_routers)
        shell = self.ssh_client.invoke_shell()
        bgp_messages = self.vm.bgp_messages(shell, random_router)
        test.add_feedback(f"Randonly checking BGP messages on {random_router}\n")
        expected_bgp_prefixes = ["11.0.0.0", "12.0.0.0", "13.0.0.0", "14.0.0.0", "15.0.0.0"]
        for prefix in expected_bgp_prefixes:
            if prefix not in bgp_messages:
                test.add_error(-5, f"Missing prefix: {prefix}, please check connectivity between routers and BGP configuration, -5 points")
                success = False

        test.add_feedback(f"BGP messages for reference: \n{bgp_messages}")
        test.set_passed(success)
        return success

    def _test_default_website(self) -> bool:
        test = self.tests["default_website"]
        test.set_to_max_score()
        success = True

        all_hosts = ["h2-1", "h3-1", "h4-1", "h5-1"]
        selected_host = random.sample(all_hosts, 2)
        test.add_feedback(f"Checking on randomly selected hosts: {selected_host}\n")

        for host in selected_host:
            shell = self.ssh_client.invoke_shell()
            output = self.vm.check_website(shell, host)
            print(f"Test Default website on {host}: \n{output}")


            if "Default" not in output:
                test.add_error(-20, f"Can't reach the default website on host {host}, -20 Points\n")
                test.add_feedback(f"{host} output for reference: \n{output}")
                success = False
            else:
                if self.anti_cheating_secret not in output:
                    test.add_error(-test.max_score, self.anti_hardcode_msg)
                    test.add_feedback(f"{host} output for reference: \n{output}")
                    success = False
                    break

        test.set_passed(success)
        return success

    def _test_rouge_website(self):
        test = self.tests["rouge_website"]
        test.set_to_max_score()

        success = True
        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, "h5-1")
        print(f"Test rogue output on h5-1: {output}")
        test.add_feedback("Checking hijack on host: h5-1\n")

        # Check if the attacker website is reachable on h5-1
        if "Attacker" not in output:
            test.add_error(-40, "Can't reach attacker website on h5-1, BGP Hijacking failed, -40 Points")
            test.add_feedback(f"output for reference: \n{output}")
            success = False
        else:
            if self.anti_cheating_secret not in output:
                test.add_error(-test.max_score, self.anti_hardcode_msg)
                test.add_feedback(f"output for reference: \n{output}")
                success = False

        # Check if the default website is reachable on h2-1
        all_hosts = ["h2-1", "h3-1"]
        host = random.choice(all_hosts)
        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, host)
        print(f"Test rogue output on {host}: {output}")
        test.add_feedback(f"Checking default on host: {host}\n")

        if "Default" not in output:
            test.add_error(-40, f"Can't reach default website on {host}, BGP Hijacking failed, -40 Points")
            test.add_feedback(f"output for reference: \n{output}")
            success = False
        else:
            if self.anti_cheating_secret not in output:
                test.add_error(-test.max_score, self.anti_hardcode_msg)
                test.add_feedback(f"output for reference: \n{output}")
                success = False

        test.set_passed(success)
        return success

    def _test_default_website_after_rouge(self) -> bool:
        test = self.tests["default_website_after"]
        test.set_to_max_score()
        success = True

        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, "h5-1")
        print(f"Test default after rogue: {output}")

        if "Default" not in output:
            test.add_error(-5, "Can't reach the default website after stopping rogue, -5 Points")
            test.add_feedback(f"output for reference: \n{output}")
            success = False

        test.set_passed(success)
        return success

    def _test_rouge_hard(self):
        test = self.tests["rouge_hard"]
        test.set_to_max_score()
        success = True

        all_hosts = ["h2-1", "h3-1", "h4-1", "h5-1"]
        selected_host = random.sample(all_hosts, 2)
        test.add_feedback(f"Checking on randomly selected hosts: {selected_host}\n")

        for host in selected_host:
            shell = self.ssh_client.invoke_shell()
            output = self.vm.check_website(shell, host)
            print(f"Test rogue hard on {host}: {output}")

            # Check if the attacker website is reachable on h5-1
            if "Attacker" not in output:
                test.add_error(-test.max_score, f"Can't reach attacker website on {host}, BGP Hijacking failed, -20 Points")
                test.add_feedback(f"output for reference: \n{output}")
                success = False
                break
            else:
                if self.anti_cheating_secret not in output:
                    test.add_error(-test.max_score, self.anti_hardcode_msg)
                    test.add_feedback(f"output for reference: \n{output}")
                    success = False
                    break

        # Check if the default website is reachable on h1-1
        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, "h1-1")
        print(f"Test rogue hard on h1-1 (should be  default): {output}")

        if "Default" not in output:
            test.add_error(-20, "Can't reach default website on h1-1, BGP Hijacking failed, -20 Points")
            test.add_feedback(f"output for reference: \n{output}")
            success = False
        else:
            if self.anti_cheating_secret not in output:
                test.add_error(-test.max_score, self.anti_hardcode_msg)
                test.add_feedback(f"output for reference: \n{output}")
                success = False

        test.set_passed(success)
        return success

    def grade(self):
        # report check
        success = self._test_report()
        print("Report test success: ", success)

        # config sanity check
        success = self._test_sanity()
        print("Sanity test success: ", success)
        if not success:
            self.tests["sanity"].add_feedback("Sanity test failed, subsequent tests skipped")
            return

        self._prepare_scripts_and_folder()
        shell = self.ssh_client.invoke_shell()
        self.vm.write_file(shell, "/tmp/anti_cheating_secret5566.txt", self.anti_cheating_secret)

        result = self.vm.start_topology(self.topology_interactive_shell)
        if not result.success:
            self.tests["default_website"].add_feedback(result.message)
            return

        # test topology
        print("Testing topology")
        self._test_topology()

        # test default website
        print("Testing default website")
        self._test_default_website()

        # test rouge website
        print("Testing rogue website")
        result = self.vm.start_rogue()
        self._test_rouge_website()

        # test default website after rouge
        result = self.vm.stop_rogue()
        print("Testing default website after rogue")
        self._test_default_website_after_rouge()

        # test rouge hard
        print("Testing rogue hard")
        result = self.vm.start_rogue(use_hard=True)
        self._test_rouge_hard()

    def generate_results(self, result: Result):
        for test in self.tests.values():
            if test.score < 0:
                test.score = 0
            result.add_test(test)


def main():
    bgph_vm = BGPHVirtualMachine()
    result = Result()

    succ = bgph_vm.start_vm()
    if not succ:
        print("Failed to start mininet")
        exit(1)
    print("starting mininet VM")
    time.sleep(90)

    grader = BGPHGrader(bgph_vm)
    grader.grade()
    grader.generate_results(result)

    result.write_json()
    bgph_vm.shutdown()


if __name__ == "__main__":
    main()
