import json
from typing import Iterator, Mapping, Union


class RawDataMixin:
    class RawData:
        def __init__(
                self,
                content: Union[bytes, Iterator[bytes]],
                headers: Mapping[str, str] = None
        ):
            self.content = content
            self.headers = headers or {}

        def __iter__(self):
            for name, value in self.headers.items():
                yield f'{name}: {value}\n'.encode()
            if self.headers:
                yield '\n'.encode()
            if isinstance(self.content, bytes):
                yield self.content
            else:
                yield from self.content

    def generate_response_data(self, output_format: str, format_text):
        if output_format == 'human':
            yield format_text(str(self)).encode()
        elif isinstance(self.data, self.RawData):
            yield from self.data
        else:
            if output_format == 'json':
                serializer = json.dumps
            else:
                raise NotImplementedError(
                    'No serializer for output format: {}'.format(output_format)
                )
            yield serializer({
                'data': self.data,
                'status': self.status,
                'code': getattr(self, 'code', None),
            }).encode()
