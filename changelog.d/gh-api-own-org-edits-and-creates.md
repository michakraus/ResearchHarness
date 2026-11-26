- **`gh api`: an edit of a comment and a new pull request or issue pass in an own organisation.**
  `gh_api_writes.py` asked for `PATCH repos/<owner>/<repo>/pulls/comments/<id>` and
  `…/issues/comments/<id>`, and for `POST …/pulls` and `…/issues`, also where `<owner>` is in the
  profile's `org` list. A review agent that corrects its own reply, and an agent that opens a pull
  request through the REST API while GitHub's GraphQL fails for `gh pr create`, then waited for
  the user. These writes now pass under the same conditions as a review or a comment: an own
  `<owner>`, a plain repository name and no `--hostname`. Elsewhere they still ask.
