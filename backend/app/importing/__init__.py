"""The importer: bring outside text in (links, EPUB books, subtitle files,
Jellyfin), show its coverage before saving, then save through
`app.reader.create_text` like a paste import.

Every source turns into a `Draft`: a title and one or more parts. A preview
scores the draft against the learner model without writing anything; the PWA
shows that and posts the parts back to save them."""


class ImportProblem(ValueError):
    """A source we can't import, with a message fit to show the learner."""
