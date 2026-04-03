#!/bin/python3
from bgph_vm_ga import BGPHVirtualMachine
from results import Result, Test
from utils import all_unique
from pathlib import Path
import time
import random
import re
import shutil

class BGPHGrader:
    def __init__(self, vm: BGPHVirtualMachine) -> None:
        self.vm = vm
        self.script_path = Path(__file__).parent
        self.submission_path = Path("/autograder/submission/BGPHijacking")
        self.anti_cheating_secret = self.vm.get_anti_cheating_secret()
        self.anti_hardcode_msg = "Mismatch, please ensure connectivity and topology correctness, and don't modify webserver.py"
        self.ROGUE = "Attacker"
        self.DEFAULT = "Default"
        self.tests = {
            "report": Test("Report", max_score=5),
            "sanity": Test("Sanity and configuration test", max_score=10),
            "topology": Test("Topology, links, connectivity, BGP", max_score=30),
            "default_website": Test("Default website test", max_score=40),
            "rogue_website": Test("Rogue website test (easy)", max_score=40),
            "default_website_after": Test("Default website after rogue", max_score=5),
            "rogue_hard": Test("Rogue website test (hard)", max_score=20),
        }



    def _prepare_scripts_and_folder(self):
        print(f"==> BGPHGrader._prepare_scripts_and_folder()")
        # copy scripts to submission folder
        scripts = ["scripts/webserver.py", "scripts/start_rogue_hard.sh", "scripts/cleanup.py", "scripts/bgp_sleep"]
        for script in scripts:
            shutil.copy(self.script_path / script, self.submission_path)

        # ensure logs exists
        (self.submission_path / "logs").mkdir(exist_ok=True, )


    def _test_report(self):
        print(f"==> BGPHGrader._test_report()")
        test = self.tests["report"]
        test.set_to_max_score()
        success = True
        required_files = ["fig2_topo.pdf"]
        for file in required_files:
            if not (self.submission_path / file).exists():
                test.add_error(-5, f"Missing report file: {file}, -5 Points")
                success = False

        test.set_passed(success)
        if success:
            test.add_feedback("Report detected! Please note that we might still manually deduct points of this part if it's not legible")
        return success


    def _test_sanity(self):
        print(f"==> BGPHGrader._test_sanity()")
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
            if not (self.submission_path / file).exists():
                success = False
                test.add_error(-test.max_score, f"Missing required file: {file}, please check your folder structure")
                return success

        # check each config exists
        for file in required_configs:
            if not (self.submission_path / file).exists():
                success = False
                test.add_error(-test.max_score, f"Missing required file: {file}, please check your folder structure")
                return success

        # check the configuration files
        if not all_unique(self.submission_path, "conf/bgpd-*.conf"):
            test.add_error(-5, "Two or more bgpd conf files are identical, -5 Points")
            success = False

        test.set_passed(success)
        return success


    def _test_topology(self):
        print(f"==> BGPHGrader._test_topology()")
        test = self.tests["topology"]
        test.set_to_max_score()
        success = True

        # test switches
        test.add_feedback("Checking for Required Switches")
        log = self.vm.get_topology_start_output()
        matched_switches = re.findall(r"\*\*\* Adding switches:.*\n(.*?)\n", log)
        if not matched_switches:
            test.add_error(-test.max_score, "Could not parse switches from topology output. Check that bgp.py starts correctly.")
            test.set_passed(False)
            return False
        switches = set(matched_switches[0].split())
        expected_switches = set(["R1", "R2", "R3", "R4", "R5", "R6"])
        diff = expected_switches - switches
        if diff:
            test.add_error(-5, f"Missing Switches: {diff}, -5 Points")
            success = False

        # test links
        test.add_feedback("Checking for Required Links")
        matched_links = re.findall(r"\*\*\* Adding links:.*\n(.*?)\n", log)
        if not matched_links:
            test.add_error(-test.max_score, "Could not parse links from topology output. Check that bgp.py starts correctly.")
            test.set_passed(False)
            return False
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
            test.add_error(-5, f"Missing Links: {', '.join(str(tuple(pair)) for pair in diff)}, -5 Points")
            success = False

        available_routers = ["R1", "R2", "R3", "R4", "R5"]
        random_router = random.choice(available_routers)
        bgp_messages = self.vm.bgp_messages(random_router)

        # print out autograder debug information that might be helpful (students won't see this)
        self.vm.do_extra_checks()

        test.add_feedback(f"Randomly checking BGP messages on {random_router}\n")
        expected_bgp_prefixes = ["11.0.0.0", "12.0.0.0", "13.0.0.0", "14.0.0.0", "15.0.0.0"]
        for prefix in expected_bgp_prefixes:
            if prefix not in bgp_messages:
                test.add_error(-5, f"Missing prefix: {prefix}, please check connectivity between routers and BGP configuration, -5 points")
                success = False

        test.add_feedback(f"{random_router}: vtysh -c 'show ip bgp' output: \n{bgp_messages.strip()}")
        test.set_passed(success)
        return success


    def _check_website_from_host(self, host: str, expected: str, test: Test, deduction: int) -> bool:
        """Check that:
         1) expected keyword is present in the website output, and
         2) the anti-cheating secret is present
        Returns True if both checks pass."""
        print(f"==> BGPHGrader._check_website_from_host()")
        output = self.vm.check_website(host)
        print(f"    {host = }, {expected = }, {deduction = }: [{output}]")

        if not output or expected not in output:
            test.add_error(deduction, f"Can't reach {expected.lower()} website from {host}, {deduction} Points")
            test.add_feedback(f"{host} received: [{output.strip()}]")
            return False
        else:
            if self.anti_cheating_secret not in output:
                test.add_error(-test.max_score, self.anti_hardcode_msg)
                test.add_feedback(f"{host} received: [{output.strip()}]")
                return False

        return True


    def _test_default_website(self) -> bool:
        print(f"==> BGPHGrader._test_default_website()")
        test = self.tests["default_website"]
        test.set_to_max_score()
        success = True

        all_hosts = ["h2-1", "h3-1", "h4-1", "h5-1"]
        selected_hosts = random.sample(all_hosts, 2)
        test.add_feedback(f"Checking routing from randomly selected hosts: {selected_hosts}\n")

        for host in selected_hosts:
            if not self._check_website_from_host(host, self.DEFAULT, test, -20):
                success = False

        test.set_passed(success)
        return success

    def _test_rogue_website(self):
        print(f"==> BGPHGrader._test_rogue_website()")
        test = self.tests["rogue_website"]
        test.set_to_max_score()
        success = True

        # Check if the attacker website is reachable from h5-1
        test.add_feedback("Checking hijack from host: h5-1\n")
        if not self._check_website_from_host("h5-1", self.ROGUE, test, -40):
            success = False

        # Check if the default website is reachable from random choice of h2-1 or h3-1
        host = random.choice(["h2-1", "h3-1"])
        test.add_feedback(f"Checking default from host: {host}\n")
        if not self._check_website_from_host(host, self.DEFAULT, test, -40):
            success = False

        test.set_passed(success)
        return success


    def _test_default_website_after_rogue(self) -> bool:
        print(f"==> BGPHGrader._test_default_website_after_rogue()")
        test = self.tests["default_website_after"]
        test.set_to_max_score()
        success = True

        if not self._check_website_from_host("h5-1", self.DEFAULT, test, -5):
            success = False

        test.set_passed(success)
        return success


    def _test_rogue_hard(self):
        print(f"==> BGPHGrader._test_rogue_hard()")
        test = self.tests["rogue_hard"]
        test.set_to_max_score()
        success = True

        all_hosts = ["h2-1", "h3-1", "h4-1", "h5-1"]
        selected_hosts = random.sample(all_hosts, 2)
        test.add_feedback(f"Checking from randomly selected hosts: {selected_hosts}\n")

        for host in selected_hosts:
            if not self._check_website_from_host(host, self.ROGUE, test, -test.max_score):
                success = False

        # Check if the default website is reachable on h1-1
        if not self._check_website_from_host("h1-1", self.DEFAULT, test, -20):
            success = False

        test.set_passed(success)
        return success


    def grade(self):
        print(f"==> BGPHGrader.grade()")

        # report check
        success = self._test_report()
        print(f"\n\n###\n### Report Test Success: {success}\n###\n")

        # config sanity check
        success = self._test_sanity()
        print(f"\n\n###\n### Sanity Test Success: {success}\n###\n")
        if not success:
            self.tests["sanity"].add_feedback("Sanity test failed, subsequent tests skipped")
            return

        self._prepare_scripts_and_folder()

        result = self.vm.start_topology()
        if not result.success:
            self.tests["default_website"].add_feedback(result.message)
            return

        # test topology
        print("\n\n###\n### Testing Topology\n###\n\n")
        self._test_topology()

        time.sleep(60) # add another wait for the topology to come up

        # test default website
        print("\n\n###\n### Testing Default Website\n###\n\n")
        self._test_default_website()

        # test rogue website
        print("\n\n###\n### Testing Rogue Website\n###\n\n")
        result = self.vm.start_rogue()
        self._test_rogue_website()

        # test default website after rogue
        result = self.vm.stop_rogue()
        print("\n\n###\n### Testing Default Website After Rogue\n###\n\n")
        print("Waiting 30s for BGP re-convergence after stopping rogue")
        time.sleep(30)
        print("Testing default website after rogue")
        self._test_default_website_after_rogue()

        # test rogue hard
        print("\n\n###\n### Testing Rogue Hard\n###\n\n")
        result = self.vm.start_rogue(use_hard=True)
        self._test_rogue_hard()

    def generate_results(self, result: Result):
        for test in self.tests.values():
            if test.score < 0:
                test.score = 0
            result.add_test(test)


def main():
    version = "2026-04-02 21.55"
    print(f"==> BGPHGrader.main() -- ver. {version}")

    bgph_vm = BGPHVirtualMachine()
    result = Result()

    succ = bgph_vm.start_vm()
    if not succ:
        print("Failed to start Mininet")
        exit(1)
    print("QEMU VM w/ Mininet started")

    grader = BGPHGrader(bgph_vm)
    grader.grade()
    grader.generate_results(result)

    result.write_json()
    bgph_vm.shutdown()


if __name__ == "__main__":
    main()
