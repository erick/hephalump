import json
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class Test:
    name: str
    number: str = ""
    output: str = ""
    max_score: int = 0
    score: int = 0
    output_format: str = "text"
    status: str = "failed"
    visibility: str = "visible"

    def set_passed(self, passed: bool = True):
        if passed:
            self.status = "passed"
        else:
            self.status = "failed"

    def set_score(self, score: int):
        self.score = score

    def set_to_max_score(self):
        self.score = self.max_score

    def as_dict(self):
        return asdict(self)

    def add_error(self, deduction: int, feedback: str):
        self.score += deduction
        self.output += feedback + "\n"

    def add_feedback(self, feedback: str):
        self.output += feedback + "\n"


class Result:

    def __init__(self) -> None:
        self.tests: List[Test] = list()

    def add_test(self, test: Test):
        self.tests.append(test)

    def as_dict(self):
        results = {}
        results["tests"] = list()
        for test in self.tests:
            results["tests"].append(test.as_dict())

        return results

    def write_json(self, output="/autograder/results/results.json"):
        with open(output, "w") as json_output:
            json.dump(self.as_dict(), json_output)

