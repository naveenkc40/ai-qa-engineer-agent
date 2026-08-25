from pathlib import Path


class TestFileWriter:

    def __init__(self, output_directory="tests/generated"):
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(
            parents=True,
            exist_ok=True
        )

    def save(self, filename: str, code: str) -> Path:

        file_path = self.output_directory / filename

        file_path.write_text(
            code,
            encoding="utf-8"
        )

        return file_path