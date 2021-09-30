"""
Publish a document.
"""
import os
from pprint import pprint

from papergit.commands.base import BaseCommand
from papergit.models import PaperDoc
from papergit.errors import NoDestinationError

__all__ = [
    'PublishCommand',
    ]


class PublishCommand(BaseCommand):
    """Sync paper folder to git repos.
    """

    name = 'publish'

    def add(self, parser, command_parser):
        self.parser = parser
        command_parser.add_argument('id',
                                    help="The Paper Document to publish.")
        command_parser.add_argument(
            '--push', action='store_true', default=False,
            help="Push changes to the remote origin after commit.")

        command_parser.add_argument(
            '--sync', action='store_true', default=False,
            help="Perform complete synchronization")

    def process(self, args):
        if args.sync:
            print("Pulling existing docs...")
            renamed_docs = []
            for doc in PaperDoc.select():
                doc.fake_doc_cache()
                og_title = doc.title
                renamed = doc.get_changes()
                if renamed:
                    final_path = doc.get_final_path(og_title)
                    if final_path:
                        renamed_docs.append(final_path)

            print("Pulling the list of paper docs...")
            PaperDoc.sync_docs()
            for doci in PaperDoc.select():
                try:
                    doc = PaperDoc.get(PaperDoc.id == doci)
                except PaperDoc.DoesNotExist:
                    print("Invalid Doc, please check again!")
                    continue
                try:
                    doc.doc_subfolders()
                    doc.publish(push=args.push)
                except NoDestinationError:
                    print("This Document hasn't been setup with a git repo...")
                    print("Please first add to a repo.")
                    continue

            for renamed in renamed_docs:
                print("renamed %s" % renamed_docs)
                os.remove(renamed)

        else:
            try:
                doc = PaperDoc.get(PaperDoc.id == args.id)
            except PaperDoc.DoesNotExist:
                print("Invalid Doc, please check again!")
                return

            try:
                doc.publish(push=args.push)
            except NoDestinationError:
                print("This Document hasn't been setup with a git repo...")
                print("Please first add to a repo.")
                return
