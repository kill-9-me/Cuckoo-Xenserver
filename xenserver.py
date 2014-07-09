import logging
import subprocess
import os.path
import time
import XenAPI
import pprint

from lib.cuckoo.common.abstracts import Machinery
from lib.cuckoo.common.exceptions import CuckooMachineError

log = logging.getLogger(__name__)

class XenServer(Machinery):
	"""Virtualization layer for XenServer using XenAPI.py"""
	LABEL = "uuid"
	session = None

	def _initialize_check(self):
		# Authorize
		if not self.options.xenserver.url:
			raise CuckooMachineError("XenServer URL is missing, please add it to the config file")
		if not self.options.xenserver.username:
			raise CuckooMachineError("XenServer username is missing, please add it to the config file")
		if not self.options.xenserver.password:
			raise CuckooMachineError("XenServer password is missing, please add it to the config file")

		# Auth
		try:
			self.session = XenAPI.Session(self.options.xenserver.url)
			self.session.xenapi.login_with_password(self.options.xenserver.username, self.options.xenserver.password)
		except:
			raise CuckooMachineError("XenServer: Could not connect to XenServer")

		# Get a list of all VMS and snapshots
		vms = []
		snapshots = []
		vmlist = self.session.xenapi.VM.get_all_records()
		for vm in vmlist:
			if vmlist[vm]["is_a_template"] or vmlist[vm]["is_a_snapshot"] or vmlist[vm]["is_control_domain"]:
				continue 
			vms.append(vmlist[vm]["uuid"])
			for snapshot in vmlist[vm]["snapshots"]:
				snapshots.append(vmlist[snapshot]["uuid"])
		# Test all machines
		for machine in self.machines():
			uuid = machine.label
			if uuid not in vms:
				raise CuckooMachineError("XenServer: VM with UUID: %s does not exist" % (uuid))
			snapshot = self._snapshot_from_vm(uuid)
			if snapshot not in snapshots:
				raise CuckooMachineError("XenServer: SnapShot with UUID: %s does not exist" % (uuid))

		# Base Checks
		super(XenServer, self)._initialize_check()

	def start(self, uuid):
		"""Start a virtual machine.
		@param uuid: UUID of Virtual Machine to use.
		@raise CuckooMachineError: if unable to start.
		"""
		# Is it already running?
		if self._is_running(uuid):
			raise CuckooMachineError("XenServer: VM %s is already running" % (uuid))
		
		self._revert(uuid)	
		
		log.debug("Starting vm %s" % uuid)
		# Start the VM
		vm = self.session.xenapi.VM.get_by_uuid(uuid)
		try:
			self.session.xenapi.VM.start(vm, False, True)
		except:
			raise CuckooMachineError("XenServer: Could not start VM %s" % (uuid))

	def stop(self, uuid):
		"""Stops a virtual machine.
		@param uuid: UUID of Virtual machine to use.
		@raise CuckooMachineError: if unable to stop
		"""
		# check to see if the VM is running
		if self._is_running(uuid):
			try:
				vm = self.session.xenapi.VM.get_by_uuid(uuid)
				self.session.xenapi.VM.hard_shutdown(vm)
			except:
				raise CuckooMachineError("XenServer: Could not shut down VM %s" % (uuid))
		else:
			log.warning("Trying to stop an already stopped VM: %s" %(uuid))


	def _revert(self, uuid):
		"""Reverts machine to snapshot.
		@param uuid: UUID of Virtual Machine to revert
		@param snapshot_uuid: UUID of Snapshot to revert to
		@raise CuckooMachineError: if unable to revert
		"""
		# Try and revert it
		log.debug("Revert snapshot for vm %s" % uuid)

		try:
			snapshot = self._snapshot_from_vm(uuid)
			self.session.xenapi.VM.revert(self.session.xenapi.VM.get_by_uuid(snapshot))
		except:
			raise CuckooMachineError("XenServer: Could not revert VM %s to snapshot %s" % (uuid,snapshot))
		log.debug("Starting vm %s" % uuid)

	def _is_running(self, uuid):
		vm = self.session.xenapi.VM.get_by_uuid(uuid)
		props = self.session.xenapi.VM.get_record(vm)
		return props["power_state"] == "Running"
		

	def _snapshot_from_vm(self, uuid):
		"""Get snapshot for a given uuid
		@param uuid: config option
		"""
		vm_info = self.db.view_machine_by_label(uuid)
		return vm_info.snapshot	
