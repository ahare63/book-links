"""Turn a detector score, the judge's verdict and the owner's review into a status and confidence.

The owner's review outranks the judge, and the judge outranks the detector. Unreviewed links never
score above UNREVIEWED_CEILING, so an accepted review always ranks first.
"""

UNREVIEWED_CEILING = 0.9
PROPOSED_CEILING = 0.5


def assess(score, judgement=None, review=None):
    """Return ``(confidence, status)``.

    ``judgement`` and ``review`` are rows (or None) with a ``verdict`` of accept or reject;
    a judgement also carries the judge's own ``confidence`` in that verdict.
    """
    if review is not None:
        if review["verdict"] == "reject":
            return 0.0, "rejected"
        return 0.95 + 0.05 * score, "accepted"
    if judgement is not None:
        if judgement["verdict"] == "reject":
            return 0.1 * score * (1 - judgement["confidence"]), "rejected"
        blended = 0.3 * score + 0.7 * judgement["confidence"]
        return PROPOSED_CEILING + (UNREVIEWED_CEILING - PROPOSED_CEILING) * blended, "accepted"
    return PROPOSED_CEILING * score, "proposed"
