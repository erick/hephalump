alias dir='ls -lAF'
alias qq='ssh mininet@localhost -p 8022'
alias qemu_start='cd /autograder/source && python3 -c "
from bgph_vm import BGPHVirtualMachine
vm = BGPHVirtualMachine()
vm.start_vm()"'
