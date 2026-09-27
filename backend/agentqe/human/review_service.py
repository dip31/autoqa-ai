from agentqe.human.review import HumanReview
from agentqe.storage.repository import AgentQERepository


class HumanReviewService:

    def __init__(self):
        self.review = HumanReview()
        self.repository = AgentQERepository()

    def submit_review(
        self,
        run_id: int,
        decision: str,
        feedback: str = "",
        cycle: int = 1,
    ):
        """
        Validate the human decision and persist it.
        """

        review = self.review.create_review(
            run_id=run_id,
            decision=decision,
            feedback=feedback,
            cycle=cycle,
        )

        self.repository.save_human_review(
            run_id=run_id,
            decision=review["decision"],
            feedback=review["feedback"],
            cycle=cycle,
        )

        return review