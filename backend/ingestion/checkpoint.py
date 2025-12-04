"""
Checkpoint Management for Document Ingestion

Tracks phase completion to enable resumable ingestion of large documents.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PhaseStatus(Enum):
    """Status of an ingestion phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PhaseInfo:
    """Information about a single phase."""

    status: PhaseStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


class IngestionCheckpoint:
    """
    Manages checkpoint state for document ingestion.

    Tracks completion status of each phase to enable resumability.
    Checkpoint file is stored alongside the PDF in the same directory.
    """

    PHASES = [
        "extract_text",
        "extract_images",
        "extract_full_pages",
        "describe_images",
        "describe_pages",
        "embed_text_chunks",
        "embed_images",
        "embed_full_pages",
        "cross_reference",
        "index_opensearch",
    ]

    def __init__(self, pdf_path: Path):
        """
        Initialize checkpoint for a PDF document.

        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = Path(pdf_path)
        self.pdf_dir = self.pdf_path.parent
        self.checkpoint_file = self.pdf_dir / "checkpoint.json"

        # Initialize phase states
        self.phases: Dict[str, PhaseInfo] = {}
        self.document_id = self.pdf_path.stem
        self.created_at: Optional[str] = None

        # Load existing checkpoint if present
        if self.checkpoint_file.exists():
            self.load()
        else:
            self._initialize_phases()

    def _initialize_phases(self):
        """Initialize all phases as pending."""
        self.created_at = datetime.utcnow().isoformat()
        for phase in self.PHASES:
            self.phases[phase] = PhaseInfo(status=PhaseStatus.PENDING)

    def load(self) -> bool:
        """
        Load checkpoint from disk.

        Returns:
            True if checkpoint was loaded successfully
        """
        try:
            with open(self.checkpoint_file, "r") as f:
                data = json.load(f)

            self.document_id = data.get("document_id", self.document_id)
            self.created_at = data.get("created_at")

            # Load phase information
            phases_data = data.get("phases", {})
            for phase_name, phase_data in phases_data.items():
                self.phases[phase_name] = PhaseInfo(
                    status=PhaseStatus(phase_data.get("status", "pending")),
                    started_at=phase_data.get("started_at"),
                    completed_at=phase_data.get("completed_at"),
                    error=phase_data.get("error"),
                    metadata=phase_data.get("metadata", {}),
                )

            logger.info(f"Loaded checkpoint from {self.checkpoint_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            self._initialize_phases()
            return False

    def save(self):
        """Save checkpoint to disk."""
        try:
            data = {
                "document_id": self.document_id,
                "pdf_path": str(self.pdf_path),
                "created_at": self.created_at,
                "updated_at": datetime.utcnow().isoformat(),
                "phases": {
                    phase_name: {
                        "status": phase_info.status.value,
                        "started_at": phase_info.started_at,
                        "completed_at": phase_info.completed_at,
                        "error": phase_info.error,
                        "metadata": phase_info.metadata,
                    }
                    for phase_name, phase_info in self.phases.items()
                },
            }

            with open(self.checkpoint_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved checkpoint to {self.checkpoint_file}")

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise

    def is_phase_completed(self, phase_name: str) -> bool:
        """
        Check if a phase has been completed.

        Args:
            phase_name: Name of the phase

        Returns:
            True if phase is completed
        """
        if phase_name not in self.phases:
            return False
        return self.phases[phase_name].status == PhaseStatus.COMPLETED

    def mark_phase_started(self, phase_name: str):
        """
        Mark a phase as started.

        Args:
            phase_name: Name of the phase
        """
        if phase_name not in self.phases:
            self.phases[phase_name] = PhaseInfo(status=PhaseStatus.IN_PROGRESS)
        else:
            self.phases[phase_name].status = PhaseStatus.IN_PROGRESS
        self.phases[phase_name].started_at = datetime.utcnow().isoformat()
        self.save()

    def mark_phase_completed(self, phase_name: str, metadata: Optional[Dict] = None):
        """
        Mark a phase as completed.

        Args:
            phase_name: Name of the phase
            metadata: Optional metadata about phase completion
        """
        if phase_name not in self.phases:
            self.phases[phase_name] = PhaseInfo(status=PhaseStatus.COMPLETED)
        else:
            self.phases[phase_name].status = PhaseStatus.COMPLETED
        self.phases[phase_name].completed_at = datetime.utcnow().isoformat()
        if metadata:
            self.phases[phase_name].metadata = metadata
        self.save()
        logger.info(f"Phase '{phase_name}' completed")

    def mark_phase_failed(self, phase_name: str, error: str):
        """
        Mark a phase as failed.

        Args:
            phase_name: Name of the phase
            error: Error message
        """
        if phase_name not in self.phases:
            self.phases[phase_name] = PhaseInfo(status=PhaseStatus.FAILED)
        else:
            self.phases[phase_name].status = PhaseStatus.FAILED
        self.phases[phase_name].error = error
        self.save()
        logger.error(f"Phase '{phase_name}' failed: {error}")

    def get_phase_status(self, phase_name: str) -> PhaseStatus:
        """
        Get status of a phase.

        Args:
            phase_name: Name of the phase

        Returns:
            PhaseStatus enum value
        """
        if phase_name not in self.phases:
            return PhaseStatus.PENDING
        return self.phases[phase_name].status

    def get_completed_phases(self) -> list[str]:
        """
        Get list of completed phase names.

        Returns:
            List of completed phase names
        """
        return [
            phase_name
            for phase_name, phase_info in self.phases.items()
            if phase_info.status == PhaseStatus.COMPLETED
        ]

    def reset(self):
        """Reset all phases to pending and delete checkpoint file."""
        self._initialize_phases()
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            logger.info(f"Deleted checkpoint file: {self.checkpoint_file}")

    def get_summary(self) -> str:
        """
        Get a summary of checkpoint status.

        Returns:
            String summary of phase completion
        """
        completed = sum(1 for p in self.phases.values() if p.status == PhaseStatus.COMPLETED)
        total = len(self.phases)
        lines = [
            f"Checkpoint Summary ({completed}/{total} phases completed):",
            f"Document: {self.document_id}",
            f"PDF: {self.pdf_path}",
            "",
            "Phases:",
        ]

        for phase_name in self.PHASES:
            phase_info = self.phases.get(phase_name)
            if phase_info:
                status_symbol = {
                    PhaseStatus.PENDING: "○",
                    PhaseStatus.IN_PROGRESS: "◐",
                    PhaseStatus.COMPLETED: "●",
                    PhaseStatus.FAILED: "✗",
                }.get(phase_info.status, "?")

                status_text = f"{status_symbol} {phase_name}: {phase_info.status.value}"
                if phase_info.metadata:
                    metadata_str = ", ".join(f"{k}={v}" for k, v in phase_info.metadata.items())
                    status_text += f" ({metadata_str})"
                lines.append(f"  {status_text}")

        return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example with PDF path
    pdf_path = Path(
        "data/knowledge_base/swing_trading/how_to_make_money_in_stocks/how_to_make_money_in_stocks.pdf"
    )

    checkpoint = IngestionCheckpoint(pdf_path)

    # Simulate phase execution
    checkpoint.mark_phase_started("extract_text")
    checkpoint.mark_phase_completed("extract_text", metadata={"chunks": 150})

    checkpoint.mark_phase_started("extract_images")
    checkpoint.mark_phase_completed("extract_images", metadata={"images": 45})

    print(checkpoint.get_summary())
