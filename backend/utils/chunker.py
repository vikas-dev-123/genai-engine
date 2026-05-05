"""Text chunking utilities for RAG."""

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import settings


class TextChunker:
    """Split long documents into overlapping chunks with metadata."""

    def __init__(self) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", "!", "?", " ", ""],
        )

    def chunk_text(self, text: str, metadata: dict | None = None) -> list[Document]:
        """Chunk plain text into LangChain Documents."""
        meta = metadata or {}
        return self._splitter.create_documents([text], metadatas=[meta])

    def chunk_by_page(self, pages: list[tuple[int, str]]) -> list[Document]:
        """Chunk each page separately preserving page numbers in metadata."""
        out: list[Document] = []
        for page_number, page_text in pages:
            docs = self._splitter.create_documents(
                [page_text],
                metadatas=[{"page_number": page_number}],
            )
            out.extend(docs)
        return out


chunker = TextChunker()
