import time
import json
import socket
import base64
import hashlib
import subprocess
from pathlib import Path
from utils import CommandResult


class BGPHVirtualMachine:
    def __init__(self) -> None:
        self.topology_start_output = ""
        self.submission_dir = Path("/autograder/submission/BGPHijacking")
        self.SSH_FWD_PORT = 8022
        self.ga_socket_path = "/tmp/qemu-ga.sock"
        self.monitor_socket_path = "/tmp/qemu-monitor.sock"
        self.anti_cheating_secret = hashlib.sha256(f"CS6250{time.time()}666".encode()).hexdigest()[0:16]


    def start_vm(self):
        print(f"\n==> BGPHVirtualMachine.start_vm()")

        qemu_command = [
            "qemu-system-x86_64",
            "-m", "1536",
            "-display", "none",
            "-serial", "none",
            "-monitor", f"unix:{self.monitor_socket_path},server,nowait",
            "-device", "virtio-net-pci,netdev=net0",
            "-netdev", f"user,id=net0,net=192.168.101.0/24,hostfwd=tcp::{self.SSH_FWD_PORT}-:22",
            "-virtfs", "local,id=hostshare,path=/autograder/submission,mount_tag=submission,security_model=none",
            "-device", "virtio-serial",
            "-chardev", f"socket,id=qga0,path={self.ga_socket_path},server=on,wait=off",
            "-device", "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0",
            "-drive", "file=/autograder/source/mininet-vm-x86_64.qcow2,format=qcow2",
            "-no-reboot",
            "-D", "/tmp/qemu-debug.log", "-d", "guest_errors,unimp",
        ]

        print("\n\n###\n### QEMU Startup Command\n###")
        print(f"{' '.join(qemu_command)}\n\n")

        try:
            self.qemu_process = subprocess.Popen(
                qemu_command,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except (OSError, FileNotFoundError) as e:
            print(f"==> QEMU VM Failed to Start:\n{e}")
            return False

        # Check QEMU didn't exit immediately
        time.sleep(3)
        if self.qemu_process.poll() is not None:
            stdout_output = self.qemu_process.stdout.read().decode()
            stderr_output = self.qemu_process.stderr.read().decode()
            print(f"==> QEMU Exited Immediately (code {self.qemu_process.returncode})")
            print(f"STDERR:\n{stderr_output}")
            return False

        # Wait for the guest agent to become available
        print("\n\n###\n### Waiting for QEMU Guest Agent\n###")
        if not self._wait_for_ga(total_wait=600, interval=10):
            print("==> Guest agent never responded - exiting")
            return False

        print(f"{self.qemu_monitor_cmd('info network')}\n\n")

        # we have a working guest agent, now do initial setup
        print("\n\n###\n### Setup for Grading\n###\n\n")
        init_cmds = [
            f"sudo mkdir -p {self.submission_dir.parent}",
            # mount the submission directory via 9p virtfs
            f"sudo mount -t 9p -o trans=virtio,msize=262144 submission {self.submission_dir.parent}",
            f"cd {self.submission_dir} && sudo chmod +x *.sh",
            f"echo '{self.anti_cheating_secret}' > /tmp/anti_cheating_secret5566.txt",
            f"ls -lAFgR {self.submission_dir}",  # Debug: show submission contents
        ]
        for cmd in init_cmds:
            ret, out, err = self.ga_exec(cmd)
            # print(f"    > {cmd} ({ret = })\nSTDOUT:\n{out.strip()}\nSTDERR:\n{err.strip()}")
            print(f"    > {cmd} ({ret = })")
            if out:
                print(f"STDOUT:\n{out.strip()}")
            if err:
                print(f"STDERR:\n{err.strip()}")
        # ret, out, err = self.ga_exec(f"sudo mkdir -p {self.submission_dir.parent}")
        # ret, out, err = self.ga_exec(f"sudo mount -t 9p -o trans=virtio,msize=262144 submission {self.submission_dir.parent}")
        # ret, out, err = self.ga_exec(f"cd {self.submission_dir} && sudo chmod +x *.sh")
        # ret, out, err = self.ga_exec(f"echo '{self.anti_cheating_secret}' > /tmp/anti_cheating_secret5566.txt")
        # ret, out, err = self.ga_exec(f"ls -lAFgR {self.submission_dir}")  # Debug: show submission contents

        return True

    ## Guest Agent Communication

    def _ga_command(self, cmd_dict, timeout=30):
        """Send a command to the QEMU guest agent and return the parsed response."""
        print(f"\n==> BGPHVirtualMachine._ga_command()\n    > {cmd_dict} @ {time.asctime(time.localtime())}")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.ga_socket_path)
        s.settimeout(timeout)
        s.sendall(json.dumps(cmd_dict).encode() + b"\n")
        data = b""
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                result = json.loads(data.decode())
                s.close()
                if "error" in result:
                    print(f"     GA error: {result['error']}")
                return result
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            except socket.timeout:
                break
        s.close()
        if data:
            print(f"    < {json.loads(data.decode())}")  # TODO: remove
            return json.loads(data.decode())
        raise RuntimeError(f"No response from guest agent for: {cmd_dict}")

    def _ga_ping(self) -> bool:
        print(f"\n==> BGPHVirtualMachine._ga_ping()")
        try:
            result = self._ga_command({"execute": "guest-ping"}, timeout=5)
            return "return" in result
        except Exception:
            return False

    def _wait_for_ga(self, total_wait=600, interval=10) -> bool:
        """Wait for the guest agent to respond to pings."""
        print(f"\n==> BGPHVirtualMachine._wait_for_ga()")
        deadline = time.time() + total_wait
        while time.time() < deadline:
            if self._ga_ping():
                print("\n\n###\n### QEMU VM Ready\n###\n\n")
                return True
            time.sleep(interval)
        return False

    def ga_exec_bg(self, command):
        """Execute a shell command inside the VM via the guest agent, fully detached. Returns the GA pid."""
        print(f"\n==> BGPHVirtualMachine.ga_exec_bg()\n    > {command} @ {time.asctime(time.localtime())}")
        cmd = {
            "execute": "guest-exec",
            "arguments": {
                "path": "/bin/bash",
                "arg": ["-c", command],
                "capture-output": False,
            }
        }

        result = self._ga_command(cmd)
        pid = result["return"]["pid"]
        print(f"\n    [background {pid = }]\n")
        return pid


    def ga_exec(self, command, timeout=60):
        """Execute a shell command inside the VM via the guest agent. Returns [exitcode, stdout, stderr]."""
        print(f"\n==> BGPHVirtualMachine.ga_exec()\n    > {command} @ {time.asctime(time.localtime())}")
        cmd = {
            "execute": "guest-exec",
            "arguments": {
                "path": "/bin/bash",
                "arg": ["-c", command],
                "capture-output": True,
            }
        }

        result = self._ga_command(cmd)
        print(f"    < {result}")  # TODO: remove
        pid = result["return"]["pid"]

        # Poll for completion
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._ga_command({
                "execute": "guest-exec-status",
                "arguments": {"pid": pid}
            })
            if status["return"]["exited"]:
                ret = status["return"]
                exitcode = ret.get("exitcode", -1)
                stdout = base64.b64decode(ret.get("out-data", "")).decode() if ret.get("out-data") else ""
                stderr = base64.b64decode(ret.get("err-data", "")).decode() if ret.get("err-data") else ""
                print(f"\n    [{exitcode = }] @ {time.asctime(time.localtime())}\n")
                return [exitcode, stdout, stderr]
            time.sleep(5)

        print(" (timed out)")
        return [-1, "", f"Command timed out after {timeout}s"]


    ## QEMU Monitor

    def qemu_monitor_cmd(self, cmd: str) -> str:
        """Send a command to the QEMU monitor via Unix socket."""
        print(f"\n==> BGPHVirtualMachine.qemu_monitor_cmd()\n    > {cmd} @ {time.asctime(time.localtime())}")
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.monitor_socket_path)
            s.settimeout(5)
            s.recv(1024)  # consume the "(qemu) " prompt
            s.send((cmd + "\n").encode())
            time.sleep(1)
            response = s.recv(4096).decode()
            s.close()
            return response
        except (OSError, socket.timeout) as e:
            return f"Monitor error: {e}"


    ## VM lifecycle

    def shutdown(self):
        print(f"\n==> BGPHVirtualMachine.shutdown()")
        try:
            self.ga_exec("sudo shutdown -h now", timeout=5)
        except Exception:
            pass  # VM is shutting down, connection will drop

    def get_anti_cheating_secret(self) -> str:
        print(f"\n==> BGPHVirtualMachine.get_anti_cheating_secret()")
        return self.anti_cheating_secret

    def get_topology_start_output(self):
        print(f"\n==> BGPHVirtualMachine.get_topology_start_output()")
        return self.topology_start_output


    ## Topology management

    def start_topology(self, total_timeout=240) -> CommandResult:
        print(f"\n==> BGPHVirtualMachine.start_topology()")

        ret, out, err = self.ga_exec(f"cd {self.submission_dir} && sudo python3 bgp.py --scriptfile /dev/null", timeout=total_timeout)
        # ret, out, err = self.ga_exec(f"sudo python3 {bgp_py} {script} > {outfile} 2>&1", timeout=total_timeout)
        # f"cd {self.submission_dir} && sudo nohup python3 bgp.py > /tmp/bgp_output.log 2>&1 & disown", timeout=10)

        self.topology_start_output = f"{err}\n\n{out}".strip()
        print(f"\n\n{self.topology_start_output}\n\n")

        # clean up processes and start the topology in the background
        ret, out, err = self.ga_exec(f"cd {self.submission_dir} && sudo python3 cleanup.py", timeout=120)
        self.ga_exec_bg(f"cd {self.submission_dir} && sudo nohup python3 bgp.py --scriptfile bgp_sleep & disown")

        time.sleep(90)

        if "*** Starting CLI:" in self.topology_start_output:
            return CommandResult(True)
        else:
            _out = self.topology_start_output
            self.topology_start_output = None
            return CommandResult(False, f"Topology did not start within {total_timeout}s, output: {_out}")


    ## Rogue AS management

    def start_rogue(self, use_hard=False) -> CommandResult:
        print(f"\n==> BGPHVirtualMachine.start_rogue()")
        script = "start_rogue_hard.sh" if use_hard else "start_rogue.sh"
        ret, out, err = self.ga_exec(f"cd {self.submission_dir} && bash ./{script}")
        time.sleep(5)
        return CommandResult(ret == 0, err if ret != 0 else "")

    def stop_rogue(self) -> CommandResult:
        print(f"\n==> BGPHVirtualMachine.stop_rogue()")
        ret, out, err = self.ga_exec(f"cd {self.submission_dir} && bash ./stop_rogue.sh")
        time.sleep(5)
        return CommandResult(ret == 0, err if ret != 0 else "")


    ## Test Helpers

    def check_website(self, host="h5-1") -> str:
        print(f"\n==> BGPHVirtualMachine.check_website()")
        ret, out, err = self.ga_exec(
            f"sudo python3 {self.submission_dir}/run.py --node {host} --cmd 'curl -s 11.0.1.1'")
        return out

    def bgp_messages(self, router="R3") -> str:
        print(f"\n==> BGPHVirtualMachine.bgp_messages()")
        ret, out, err = self.ga_exec(
            f"sudo python3 {self.submission_dir}/run.py --node {router} --cmd \"vtysh -c 'show ip bgp'\"")
        return out

    def do_extra_checks(self):
        """
        print out autograder debug information that might be helpful (students won't see this)
        no need to return anything
        """
        print(f"\n==> BGPHVirtualMachine.do_extra_checks()")
        debug_info_cmds = [
            # "ps -ef | grep webserver",
            # "ls -lAF /tmp/anti_cheating_secret5566.txt",
        ]
        if not debug_info_cmds:
            print(f"    No extra checks being run right now")
        for cmd in debug_info_cmds:
            ret, out, err = self.ga_exec(cmd)
            print(f"    > {cmd} (retcode = {ret})\nSTDOUT:\n{out.strip()}\nSTDERR:\n{err.strip()}")
