"""
"""
import os
import time
import re
import dropbox.exceptions

from dropbox.paper import ExportFormat
from git import Repo, GitCommandError
from papergit.errors import NoDestinationError, DocDoesNotExist
from papergit.utilities.dropbox import dropbox_api
from papergit.utilities.modules import create_file_name
from papergit.utilities.general import generate_metadata
from papergit.config import config
from peewee import (Model, CharField, ForeignKeyField, IntegerField,
                    TimestampField, PrimaryKeyField)

__all__ = [
    'PaperDoc',
    'PaperFolder',
    'Sync',
]


class BasePaperModel(Model):
    """This is base model from Dropbox Paper. All the paper documents
    be it folder or document subclass this. It provides some very basic
    functionalities.
    """

    class Meta:
        database = config.db.db


class PaperFolder(BasePaperModel):
    """Representation of a Dropbox Paper folder"""
    name = CharField()
    folder_id = CharField()

    def __repr__(self):
        return "Folder {}".format(self.name)


class PaperDoc(BasePaperModel):
    """Representation of a Dropbox Paper document."""
    title = CharField()
    paper_id = CharField()
    version = IntegerField(default=0)
    folder = ForeignKeyField(PaperFolder, null=True, related_name='docs')
    last_updated = TimestampField()
    last_published = TimestampField(null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return "{}: Document {} at version {}".format(
            self.id, self.title, self.version)

    @classmethod
    def get_by_paper_id(self, paper_id):
        return PaperDoc.get(PaperDoc.paper_id == paper_id)

    def get_changes(self):
        """Update this record with the latest version of the document. Also,
        download the latest version to the file.
        """
        renamed = False
        title, rev, is_draft = PaperDoc.download_doc_unless_draft(self.paper_id, "")
        if not is_draft and rev > self.version:
            print('Update revision for doc {0} from {1} to {2}'.format(
                self.title, self.version, rev))
            self.version = rev
            self.last_updated = time.time()
        if self.title != title:
            renamed = True
            self.title = title
            self.last_updated = time.time()
        self.save()
        self.update_folder_info()
        return renamed

    @classmethod
    def generate_file_path(self, doc_id):
        return os.path.join(config.CACHE_DIR, doc_id + '.md')

    @classmethod
    @dropbox_api
    def sync_docs(self, dbx):
        """Fetches all the doc ids from the given dropbox handler.
        Args:
            dbx(dropbox.Dropbox): an instance of initialized dropbox handler
        Returns:
            An array of all the doc ids.
        """
        docs = dbx.paper_docs_list()
        for doc_id in docs.doc_ids:
            if not self.is_included_in_sync(doc_id):
                continue
            try:
                doc = PaperDoc.get(PaperDoc.paper_id == doc_id)
                if not os.path.exists(self.generate_file_path(doc_id)):
                    title, rev, is_draft = self.download_doc_unless_draft(doc_id, "")
                    if is_draft:
                        continue
            except PaperDoc.DoesNotExist:
                title, rev, is_draft = self.download_doc_unless_draft(doc_id, "")
                if is_draft:
                    continue
                doc = PaperDoc.create(paper_id=doc_id, title=title, version=rev,
                                      last_updated=time.time())
                doc.update_folder_info()
                print(doc)

    @classmethod
    @dropbox_api
    def download_doc(self, dbx, doc_id):
        """Downloads the given doc_id to the local file cache.
        """
        path = self.generate_file_path(doc_id)
        result = dbx.paper_docs_download_to_file(
            path, doc_id, ExportFormat.markdown)
        return (result.title, result.revision)

    def get_final_path(self, title):
        """Downloads the given doc_id to the local file cache.
        """
        try:
            sync = Sync.get(folder=self.folder)
            print("og title: %s" % title)
            return sync.get_final_path(self, title)
        except Sync.DoesNotExist:
            print("SYNC NOT EXIST")
            return ""
        except DocDoesNotExist:
            print("DOC NOT EXIST")
            return ""

    @classmethod
    @dropbox_api
    def download_doc_unless_draft(self, dbx, doc_id, draft_tag="#draft"):
        """Downloads the given doc_id to the local file cache.
           Delete if draft and return whether file is draft
           We meed this, as theres no way to check metadata before downloading doc
        """
        title, rev = self.download_doc(doc_id)
        is_draft = False
        if draft_tag and draft_tag in title.lower():
            is_draft = True
            path = self.generate_file_path(doc_id)
            os.remove(path)
        return title, rev, is_draft

    @classmethod
    @dropbox_api
    def is_included_in_sync(cls, dbx, doc_id):
        folder_info = dbx.paper_docs_get_folder_info(doc_id)
        folders_synced = PaperFolder.select()
        if not folders_synced:  # No folders are synced, take everything
            return True
        if folder_info and folder_info.folders:
            for folder in folders_synced:
                if folder.name.lower() == folder_info.folders[0].name.lower():
                    return True
        return False

    @dropbox_api
    def update_folder_info(self, dbx):
        """Fetch and update the folder information for the current PaperDoc.
        """
        folders = dbx.paper_docs_get_folder_info(self.paper_id)
        if folders.folders is None:
            return
        folder = folders.folders[0]
        f = PaperFolder.get_or_create(folder_id=folder.id, name=folder.name)[0]
        self.folder = f
        self.save()

    def publish(self, push=False):
        """Publish the document as a blog post.
        Process:
        - Find if this document belongs to a PaperFolder,
        - If yes, find if that PaperFolder is a part of a Sync,
        - If yes, find if there already exists a file at the destination,
        - If no, create the file, copy it to destination
        - If yes, still copy the file to the destination
          (Later it will fail and allow to view a diff of the changes that will
           be made to the destination file.)
        """
        print(self.title)
        is_draft = "#draft"
        if is_draft in self.title.lower():
            return True
        if self.folder:
            try:
                sync = Sync.get(folder=self.folder)
                sync.try_sync_single(doc=self, commit=False, push=push)
                self.last_published = time.time()
                self.save()
            except Sync.DoesNotExist:
                raise NoDestinationError
            except DocDoesNotExist:
                self.download_doc()
                self.publish(push=push)
            return True
        raise NoDestinationError

    @property
    def sync_path(self):
        """Returns the destination path if the sync were to run on doc.
        It needs this doc to belong to a PaperFolder and that PaperFolder to be
        a part of a Sync.
        Otherwise, it returns None

        Returns (document's path, destination path)
        """
        try:
            sync = Sync.get(folder=self.folder)
            return sync.get_doc_sync_path(self)
        except Sync.DoesNotExist:
            return None
        except DocDoesNotExist:
            self.download_doc()
            return self.sync_path


class Sync(BasePaperModel):
    """Representation of a synchronization between a Git repo and a
    PaperFolder. Files are synchronized only after a few changes are made and
    the metadata is added.

    Files with #draft in them is not synchronized to the git repo.
    """
    # Path to the Git Repo.
    repo = CharField()
    # Path to the directories in the git repo.
    path_in_repo = CharField()
    folder = ForeignKeyField(PaperFolder)
    last_run = TimestampField(null=True)

    def __repr__(self):
        return "Folder {} to Git repo at {} at path {}".format(
            self.folder.name, self.repo, self.path_in_repo)

    def sync(self, commit=True, push=False):
        for doc in self.folder.docs:
            self.sync_single(doc, commit=False, push=False)
        if commit:
            self.commit_changes(push=push)

    def sync_single(self, doc, commit=True, push=False):
        original_path, final_path = self.get_doc_sync_path(doc)
        with open(final_path, 'w+') as fp:
            with open(original_path, 'r') as op:
                heading = op.readline().strip()
                first_line = op.readline().strip()

                tags = re.findall(r"#(\w+)", first_line)
                draft = 'false'
                actual_tags = []
                for tag in tags:
                    if tag == "draft":
                        draft = 'true'
                    else:
                        actual_tags.append(tag)

                print(generate_metadata(doc, None, actual_tags, draft), file=fp)
                if len(tags) == 0:
                    print(first_line, file=fp)
                print(op.read(), file=fp)

        if commit:
            self.commit_changes(push=push)

    def try_sync_single(self, doc, commit=True, push=False):
        from os.path import exists
        if exists(PaperDoc.generate_file_path(doc.paper_id)):
            self.sync_single(doc, commit, push)

    def get_doc_sync_path(self, doc):
        original_path = PaperDoc.generate_file_path(doc.paper_id)
        file_name = create_file_name(doc.title)
        final_path = os.path.join(self.repo, self.path_in_repo, file_name)
        return (original_path, final_path)

    def get_final_path(self, title):
        print("get_final_path")
        # file_name = create_file_name(title)
        # final_path = os.path.join(self.repo, self.path_in_repo, file_name)
        return title

    def commit_changes(self, push=False):
        git_repo = Repo(self.repo)
        git_repo.git.add('content/')
        try:
            git_repo.git.commit('-m', 'Commit added by PaperGit')
            self.last_run = time.time()
            self.save()
        except GitCommandError:
            print('Nothing to commit')
        if push:
            print("Pushing changes to remote")
            git_repo.git.push('origin')
