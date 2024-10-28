#!/bin/python3
from bgph_vm import BGPHVirtualMachine
from results import Result, Test
from utils import all_unique
from pathlib import Path
import time

class BGPHGrader:
    def __init__(self, vm: BGPHVirtualMachine) -> None:
        self.BGPH_path = Path("/autograder/submission/BGPHijacking")
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
            "sanity": Test("Sanity Test", max_score=20),
            "topology": Test("Topology and Connectivity", max_score=20),
            "default_website": Test("Default website test", max_score=40),
            "rouge_website": Test("Rouge website test (AS5 only)", max_score=40),
            "default_website_after": Test("Default website after rouge", max_score=5),
            "rouge_hard": Test("Rouge website test (Whole topology)", max_score=20),
        }

    def _test_report(self):
        test = self.tests["report"]
        test.set_to_max_score()
        success = True
        required_files = ["fig2_topo.pdf"]
        for file in required_files:
            if not (self.BGPH_path / file).exists():
                success = False

        test.set_passed(success)
        test.add_feedback("Please use legible configuration values! We might manually deduct points of this part if it’s not legible")
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
                test.add_error(-test.max_score, f"Missing required file: {file}, invalid submission")
                return success

        # check each config exists
        for file in required_configs:
            if not (self.BGPH_path / file).exists():
                success = False
                test.add_error(-test.max_score, f"Missing required file: {file}, invalid submission")
                return success

        # check the configuration files
        if not all_unique(self.BGPH_path, "conf/bgpd-*.conf"):
            test.add_error(-5, "One or more bgpd conf files are similar, -5 Points")
            success = False
        if not all_unique(self.BGPH_path, "conf/zebra-*.conf"):
            test.add_error(-5, "One or more zebra conf files are similar, -5 Points")
            success = False

        test.set_passed(success)
        return success

    def _test_topology(self):
        test = self.tests["topology"]
        test.set_to_max_score()
        success = True


        test.set_passed(success)
        return success

    def _test_default_website(self) -> bool:
        test = self.tests["default_website"]
        test.set_to_max_score()
        success = True

        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, "h5-1")
        print(f"Output: {output}")
        test.add_feedback(f"Output: {output}")

        if "Default" not in output:
            test.add_error(-40, "Can't reach the default website, -40 Points")
            success = False

        test.set_passed(success)
        return success

    def _test_rouge_website(self):
        test = self.tests["rouge_website"]
        test.set_to_max_score()

        success = True
        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, "h5-1")
        print(f"Output: {output}")
        test.add_feedback(f"Output: {output}")

        # Check if the attacker website is reachable on h5-1
        if "Attacker" not in output:
            test.add_error(-40, "Can't reach attacker website on h5-1, BGP Hijacking failed, -40 Points")
            success = False

        # Check if the default website is reachable on h2-1
        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, "h2-1")
        print(f"Output: {output}")
        test.add_feedback(f"Output: {output}")
        if "Default" not in output:
            test.add_error(-40, "Can't reach default website on h2-1, BGP Hijacking failed, -40 Points")
            success = False

        test.set_passed(success)
        return success

    def _test_default_website_after_rouge(self) -> bool:
        test = self.tests["default_website_after"]
        test.set_to_max_score()
        success = True

        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell)
        test.add_feedback(f"Output: {output}")
        print(f"Output: {output}")

        if "Default" not in output:
            test.add_error(-5, "Can't reach the default website after stopping rouge, -5 Points")
            success = False

        test.set_passed(success)
        return success

    def _test_rouge_hard(self):
        test = self.tests["rouge_hard"]
        test.set_to_max_score()
        success = True

        for host in ["h5-1", "h2-1"]:
            shell = self.ssh_client.invoke_shell()
            output = self.vm.check_website(shell, host)
            print(f"Output: {output}")
            test.add_feedback(f"Output: {output}")

            # Check if the attacker website is reachable on h5-1
            if "Attacker" not in output:
                test.add_error(-20, f"Can't reach attacker website on {host}, BGP Hijacking failed, -20 Points")
                success = False
                break

        # Check if the default website is reachable on h1-1
        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell, "h1-1")
        print(f"Output: {output}")
        test.add_feedback(f"Output: {output}")
        if "Default" not in output:
            test.add_error(-20, "Can't reach default website on h1-1, BGP Hijacking failed, -20 Points")
            success = False

        test.set_passed(success)
        return success

    def grade(self):
        # report check
        success = self._test_sanity()
        print("Report test success: ", success)

        # config sanity check
        success = self._test_sanity()
        print("Sanity test success: ", success)
        if not success:
            self.tests["sanity"].add_feedback("Sanity test failed, subsequent tests skipped")
            return

        result = self.vm.start_topology(self.topology_interactive_shell)
        if not result.success:
            self.tests["default_website"].add_feedback(result.message)
            return

        # test topology
        print("Testing topology")
        success = self._test_topology()
        if not success:
            self.tests["topology"].add_feedback("Topology test failed, subsequent tests skipped")
            return

        # test default website
        print("Testing default website")
        self._test_default_website()

        # test rouge website
        print("Testing rouge website")
        result = self.vm.start_rogue()
        self._test_rouge_website()

        # test default website after rouge
        result = self.vm.stop_rogue()
        print("Testing default website after rouge")
        self._test_default_website_after_rouge()

        # test rouge hard
        print("Testing rouge hard")
        result = self.vm.start_rogue(use_hard=True)
        self._test_rouge_hard()

    def generate_results(self, result: Result):
        for test in self.tests.values():
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
