# -*- coding: utf-8 -*-

import datetime
import logging
import os
import shutil
import time

from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer


class Watcher(PatternMatchingEventHandler):
    def __init__(self, tahoe, local_dir, remote_dircap, polling_frequency=20):
        super(Watcher, self).__init__(ignore_patterns=["*.gridsync-versions*"])
        self.tahoe = tahoe
        self.local_dir = os.path.expanduser(local_dir)
        self.remote_dircap = remote_dircap
        self.polling_frequency = polling_frequency
        self.versions_dir = os.path.join(self.local_dir, '.gridsync-versions')
        self.do_backup = False

    def start(self):
        self.sync()
        logging.info("Starting observer in {}...".format(self.local_dir))
        self.observer = Observer()
        self.observer.schedule(self, self.local_dir, recursive=True)
        self.observer.start()
        self.local_checker = LoopingCall(self.check_for_backup)
        self.local_checker.start(1)
        self.remote_checker = LoopingCall(self.check_for_new_snapshot)
        self.remote_checker.start(self.polling_frequency)

    def on_modified(self, event):
        self.do_backup = True
        logging.debug(event)

    def check_for_backup(self):
        if self.do_backup and not self.tahoe.parent.sync_state:
            self.do_backup = False
            reactor.callInThread(self.wait_for_writes)

    def wait_for_writes(self):
        time.sleep(1)
        if not self.do_backup:
            self.perform_backup()

    def perform_backup(self):
        remote_snapshot = self.get_latest_snapshot()
        if self.local_snapshot == remote_snapshot:
            self.sync(skip_comparison=True)
        else:
            self.sync(snapshot=remote_snapshot)

    def check_for_new_snapshot(self):
        #logging.debug("Checking for new snapshot...")
        try:
            remote_snapshot = self.get_latest_snapshot()
        except:
            # XXX This needs to be far more robust; 
            # don't assume an exception means no backups...
            logging.warning("Doing (first?) backup...")
            self.sync(skip_comparison=True)
            return
        if remote_snapshot != self.local_snapshot:
            logging.debug("New snapshot available: {}".format(remote_snapshot))
            if not self.tahoe.parent.sync_state:
                reactor.callInThread(self.sync, snapshot=latest_snapshot)

    def get_latest_snapshot(self):
        # TODO: If /Archives doesn't exist, perform (first?) backup?
        dircap = self.remote_dircap + "/Archives"
        j = self.tahoe.ls_json(dircap)
        snapshots = []
        for snapshot in j[1]['children']:
            snapshots.append(snapshot)
        snapshots.sort()
        return snapshots[-1:][0]

    def get_local_metadata(self, basedir):
        metadata = {}
        for root, dirs, files in os.walk(basedir, followlinks=True):
            for name in dirs:
                path = os.path.join(root, name)
                metadata[path] = {}
            for name in files:
                path = os.path.join(root, name)
                metadata[path] = {
                    'mtime': os.path.getmtime(path),
                    'size': os.path.getsize(path)
                }
        return metadata

    def _create_conflicted_copy(self, filename, mtime):
        base, extension = os.path.splitext(filename)
        t = datetime.datetime.fromtimestamp(mtime)
        tag = t.strftime('.(conflicted copy %Y-%m-%d %H-%M-%S)')
        newname = base + tag + extension
        shutil.copy2(filename, newname)

    def _create_versioned_copy(self, filename, mtime):
        local_filepath = os.path.join(self.local_dir, filename)
        base, extension = os.path.splitext(filename)
        t = datetime.datetime.fromtimestamp(mtime)
        tag = t.strftime('.(%Y-%m-%d %H-%M-%S)')
        newname = base + tag + extension
        versioned_filepath = os.path.join(self.versions_dir, newname)
        if not os.path.isdir(os.path.dirname(versioned_filepath)):
            os.makedirs(os.path.dirname(versioned_filepath))
        logging.info("Creating {}".format(versioned_filepath))
        shutil.copy2(local_filepath, versioned_filepath)

    def sync(self, snapshot='Latest', skip_comparison=False):
        # XXX Pause Observer here?
        if snapshot != 'Latest':
            snapshot = 'Archives/' + snapshot
        self.tahoe.parent.sync_state += 1 # Use list of syncpairs instead?
        logging.info("Syncing {} with {}...".format(self.local_dir, snapshot))
        j = self.tahoe.ls_json(self.remote_dircap)
        if skip_comparison:
            self.tahoe.backup(self.local_dir, self.remote_dircap)
            self.latest_snapshot = self.get_latest_snapshot() # XXX Race
            logging.info("Synchronized to {}".format(self.latest_snapshot))
            self.tahoe.parent.sync_state -= 1
            return
        remote_path = '/'.join([self.remote_dircap, snapshot])
        local_metadata = self.get_local_metadata(self.local_dir)
        remote_metadata = self.tahoe.get_metadata(remote_path, metadata={})
        # TODO: If tahoe.get_metadata() fails or doesn't contain a
        # valid snapshot, jump to backup?
        do_backup = False
        for file, metadata in remote_metadata.items():
            if metadata['type'] == 'dirnode':
                dirpath = os.path.join(self.local_dir, file)
                if not os.path.isdir(dirpath):
                    logging.info("Creating directory: {}...".format(dirpath))
                    os.makedirs(dirpath)
        for file, metadata in remote_metadata.items():
            if metadata['type'] == 'filenode':
                remote_filepath = file
                file = os.path.join(self.local_dir, file)
                if file in local_metadata:
                    local_mtime = int(local_metadata[file]['mtime'])
                    remote_mtime = int(metadata['mtime'])
                    if remote_mtime > local_mtime: # Remote is newer; download
                        self._create_versioned_copy(file, local_mtime)
                        self.tahoe.get(metadata['uri'], file, remote_mtime)
                    elif remote_mtime < local_mtime: # Local is newer; backup
                        do_backup = True
                    else:
                        logging.debug("{} is up to date.".format(file))
                else: # Local is missing; download
                    self.tahoe.get(metadata['uri'], file, metadata['mtime'])
        for file, metadata in local_metadata.items():
            fn = file.split(self.local_dir + os.path.sep)[1]
            if fn not in remote_metadata and self.versions_dir not in file:
                # TODO: Distinguish between local files that haven't
                # been stored and intentional (remote) deletions
                # (perhaps only polled syncs should delete?)
                logging.debug("[!] {} isn't stored; doing backup".format(file))
                do_backup = True
        if do_backup:
            self.tahoe.backup(self.local_dir, self.remote_dircap)
        self.local_snapshot = self.get_latest_snapshot() # XXX Race
        logging.info("Synchronized to {}".format(self.local_snapshot))
        self.tahoe.parent.sync_state -= 1

    def stop(self):
        logging.info("Stopping observer in {}".format(self.local_dir))
        self.local_checker.stop()
        self.remote_checker.stop()
        try:
            self.observer.stop()
            self.observer.join()
        except:
            pass
