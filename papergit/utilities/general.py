"""
"""

from string import Template
from papergit.config import config

__all__ = [
    'generate_metadata',
    ]


METADATA_TEMPLATE = Template("""\
---
title: "$title"
date: "$date"
---

""")

METADATA_TEMPLATE_HUGO = Template("""\
---
title: "$title"
date: "$date"
draft: $draft

kategorie: $categories
štítky: $tags
categories: $categories
tags: $tags
---""")

def generate_metadata(doc, metadata_type=None, tags=None, draft=None):
    """
    Generate the appropriate metadata based on the type specified.
    """
    if metadata_type is None:
        metadata_type = config.metadata.type

    if metadata_type == "yaml":
        return generate_yaml_metadata(doc)
    if metadata_type == "hugo":
        return generate_hugo_metadata(doc, tags, draft)

    raise NotImplementedError


def generate_yaml_metadata(doc):
    """
    Generate the YAML metadata to add on top of a PaperDoc when moving a
    PaperDoc to a static site generator.
    """
    return METADATA_TEMPLATE.safe_substitute(title=doc.title,
                                             date=doc.last_updated)

def generate_hugo_metadata(doc, tags, draft):
    """
    Generate the YAML metadata to add on top of a PaperDoc when moving a
    PaperDoc to a static site generator.
    """
    return METADATA_TEMPLATE_HUGO.safe_substitute(title=doc.title,
                                                  date=doc.last_updated,
                                                  categories=doc.subfolders,
                                                  tags=tags,
                                                  draft=draft,
                                                  )