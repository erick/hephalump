#!/bin/python3
from bgph_vm import BGPHVirtualMachine
from results import Result, Test
from utils import all_unique
from pathlib import Path
import time

class BGPHGrader:
    def __init__(self, vm: BGPHVirtualMachine) -> None:
        self.submission_path = Path("/autograder/submission")
        self.vm = vm
        ssh_client = self.vm.init()
        if not ssh_client:
            print("Failed to connect to the VM")
            exit(1)

        # open the shells
        self.topology_interactive_shell = ssh_client.invoke_shell()
        self.ssh_client = ssh_client

        self.tests = {
            "sanity": Test("Sanity Test", max_score=10),
            "default_website": Test("Default Route Test", max_score=40),
            "rouge_website": Test("Rouge Route Test", max_score=40)
        }

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
            if not (self.submission_path / file).exists():
                success = False
                test.add_error(-test.max_score, f"Missing required file: {file}, invalid submission")
                return success

        # check each config exists
        for file in required_configs:
            if not (self.submission_path / file).exists():
                success = False
                test.add_error(-test.max_score, f"Missing required file: {file}, invalid submission")
                return success

        # check the configuration files
        if not all_unique(self.submission_path, "conf/bgpd-*.conf"):
            test.add_error(-2, "One or more bgpd conf files are similar, -2 Points")
            success = False
        if not all_unique(self.submission_path, "conf/zebra-*.conf"):
            test.add_error(-2, "One or more zebra conf files are similar, -2 Points")
            success = False

        test.set_passed(success)
        return success

    def _test_default_website(self) -> bool:
        test = self.tests["default_website"]
        test.set_to_max_score()
        success = True

        shell = self.ssh_client.invoke_shell()
        output = self.vm.check_website(shell)
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
        output = self.vm.check_website(shell)
        if "Attacker" not in output:
            test.add_error(-40, "Can't reach attacker website, BGP Hijacking failed, -40 Points")
            test.add_error(-0, f"Output: {output}")
            success = False

        test.set_passed(success)
        return success

    def grade(self):
        success = self._test_sanity()
        if not success:
            self.tests["default_website"].add_error(-0, "Sanity test failed, subsequent tests skipped")
            return
        result = self.vm.start_topology(self.topology_interactive_shell)
        if not result.success:
            self.tests["default_website"].add_error(-0, result.message)
            return
        print(f"Sanity test result: {result}")

        self._test_default_website()

        result = self.vm.start_rogue()
        self._test_rouge_website()

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
