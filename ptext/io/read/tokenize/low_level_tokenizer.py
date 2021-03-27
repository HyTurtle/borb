# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    This module contains everything needed to perform low-level tokenization against PDF syntax.
    Low-level tokenization aims to separate numbers, strings, names, comments, start of dictionary, start of array, etc
    The high-level tokenizer will use this first pass to then build complex objects (streams, dictionaries, etc)
"""
import enum
import io
from typing import Optional


class TokenType(enum.IntEnum):
    """
    This enum represents the various kinds of Token objects the PDF parser can encounter
    """

    NUMBER = 1
    STRING = 2
    HEX_STRING = 3
    NAME = 4
    COMMENT = 5
    START_ARRAY = 6
    END_ARRAY = 7
    START_DICT = 8
    END_DICT = 9
    REF = 10
    OBJ = 11
    END_OBJ = 12
    OTHER = 13
    END_OF_FILE = 14


class Token:
    """
    This class represents a token in PDF syntax.
    A lexical token or simply token is a string with an assigned and thus identified meaning.
    It is structured as a pair consisting of a token name and an optional token value.
    The token name is a category of lexical unit.
    """

    def __init__(self, byte_offset: int, token_type: TokenType, text: str):
        self.byte_offset = byte_offset
        self.token_type = token_type
        self.text = text

    def set_byte_offset(self, byte_offset: int) -> "Token":
        """
        Set the byte offset of this Token
        """
        self.byte_offset = byte_offset
        return self

    def set_text(self, text: str) -> "Token":
        """
        Set the text of this Token
        """
        self.text = text
        return self

    def set_token_type(self, token_type: TokenType) -> "Token":
        """
        Set the TokenType of this Token
        """
        self.token_type = token_type
        return self


class LowLevelTokenizer:
    """
    In computer science, lexical analysis, lexing or tokenization is the process of converting a sequence of characters
    (such as in a computer program or web page) into a sequence of tokens (strings with an assigned and thus identified meaning).
    A program that performs lexical analysis may be termed a lexer, tokenizer, or scanner,
    although scanner is also a term for the first stage of a lexer.
    A lexer is generally combined with a parser, which together analyze the syntax of programming languages, web pages,
    and so forth.
    """

    def __init__(self, io_source):
        self.io_source = io_source

    def next_non_comment_token(self) -> Optional[Token]:
        """
        This function retrieves the next non-comment Token.
        It returns None if no such Token exists (end of stream/file)
        """
        t = self.next_token()
        while t is not None and t.token_type == TokenType.COMMENT:
            t = self.next_token()
        return t

    def next_token(self) -> Optional[Token]:
        """
        This function retrieves the next Token.
        It returns None if no such Token exists (end of stream/file)
        """
        ch = self._next_char()
        if len(ch) == 0:
            return None

        while len(ch) > 0 and self._is_whitespace(ch):
            ch = self._next_char()

        # START_ARRAY
        if ch == "[":
            return Token(self.io_source.tell() - 1, TokenType.START_ARRAY, "[")

        # END ARRAY
        if ch == "]":
            return Token(self.io_source.tell() - 1, TokenType.END_ARRAY, "]")

        # NAME
        if ch == "/":
            out_str = "/"
            out_pos = self.io_source.tell() - 1
            while True:
                ch = self._next_char()
                if len(ch) == 0:
                    break
                if self._is_delimiter(ch):
                    break
                out_str += ch
            if len(ch) != 0:
                self._prev_char()
            return Token(out_pos, TokenType.NAME, out_str)

        # END_DICT
        if ch == ">":
            out_pos = self.io_source.tell() - 1
            ch = self._next_char()
            # CHECK UNEXPECTED CHARACTER AFTER >
            assert ch == ">"
            return Token(out_pos, TokenType.END_DICT, ">>")

        # COMMENT
        if ch == "%":
            out_str = ""
            out_pos = self.io_source.tell() - 1
            while len(ch) != 0 and ch != "\r" and ch != "\n":
                out_str += ch
                ch = self._next_char()
            if len(ch) != 0:
                self._prev_char()
            return Token(out_pos, TokenType.COMMENT, out_str)

        # HEX_STRING OR DICT
        if ch == "<":
            out_pos = self.io_source.tell() - 1
            ch = self._next_char()

            # DICT
            if ch == "<":
                return Token(out_pos, TokenType.START_DICT, "<<")

            # empty hex string
            if ch == ">":
                return Token(out_pos, TokenType.HEX_STRING, "<>")

            # HEX_STRING
            out_str = "<" + ch
            while True:
                ch = self._next_char()
                if len(ch) == 0:
                    break
                out_str += ch
                if ch == ">":
                    break

            return Token(out_pos, TokenType.HEX_STRING, out_str)

        # NUMBER
        if ch in "-+.0123456789":
            out_str = ""
            out_pos = self.io_source.tell() - 1
            while len(ch) != 0 and ch in "-+.0123456789":
                out_str += ch
                ch = self._next_char()
            if len(ch) != 0:
                self._prev_char()
            return Token(out_pos, TokenType.NUMBER, out_str)

        # STRING
        if ch == "(":
            bracket_nesting_level = 1
            out_str = "("
            out_pos = self.io_source.tell() - 1
            while True:
                ch = self._next_char()
                if len(ch) == 0:
                    break
                if ch == "\\":
                    ch = self._next_char()
                    out_str += "\\" + ch
                    continue
                if ch == "(":
                    bracket_nesting_level += 1
                if ch == ")":
                    bracket_nesting_level -= 1
                out_str += ch
                if bracket_nesting_level == 0:
                    break
            assert len(ch) != 0
            assert not out_str.endswith("\\")
            return Token(out_pos, TokenType.STRING, out_str)

        # OTHER
        out_str = ""
        out_pos = self.io_source.tell() - 1
        while len(ch) != 0 and not self._is_delimiter(ch):
            out_str += ch
            ch = self._next_char()
        if len(ch) != 0:
            self._prev_char()
        return Token(out_pos, TokenType.OTHER, out_str)

    def seek(self, pos: int, whence: int = io.SEEK_SET):
        """
        Change the stream position to the given byte offset. offset is interpreted relative to the position indicated by whence.
        The default value for whence is SEEK_SET. Values for whence are:
        SEEK_SET or 0 – start of the stream (the default); offset should be zero or positive
        SEEK_CUR or 1 – current stream position; offset may be negative
        SEEK_END or 2 – end of the stream; offset is usually negative
        Return the new absolute position.
        """
        return self.io_source.seek(pos, whence)

    def tell(self) -> int:
        """
        Return the current stream position.
        """
        return self.io_source.tell()

    def _is_delimiter(self, ch: str) -> bool:
        # fmt: off
        return ord(ch) in [ -1, 0, 9, 10, 12, 13, 32, 37, 40, 41, 47, 60, 62, 91, 93,]
        # fmt: on

    def _is_whitespace(self, ch: str) -> bool:
        return ord(ch) in [0, 9, 10, 12, 13, 32]

    def _next_char(self):
        return self.io_source.read(1).decode("latin-1")

    def _prev_char(self):
        return self.io_source.seek(-1, io.SEEK_CUR)