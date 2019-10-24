import logging
import os
import math
import re
from PIL import Image

# noinspection PyPackageRequirements
from telegram import Sticker, Document
# noinspection PyPackageRequirements
from telegram.error import BadRequest, TelegramError

from ..utils import utils
from .error import EXCEPTIONS

logger = logging.getLogger(__name__)


def get_correct_size(sizes):
    i = 0 if sizes[0] > sizes[1] else 1  # i: index of the biggest size
    new = [None, None]
    new[i] = 512
    rateo = 512 / sizes[i]
    # print(rateo)
    new[1 if i == 0 else 0] = int(math.floor(sizes[1 if i == 0 else 0] * round(rateo, 4)))

    logger.debug('correct sizes: %dx%d', new[0], new[1])
    return tuple(new)


class StickerFile:
    def __init__(self, sticker, caption=None, temp_file=None):
        self._file: [Sticker, Document] = sticker
        self._emoji = None
        self._size_original = (0, 0)
        self._size_resized = (0, 0)
        self._tempfile_downloaded = temp_file or tempfile.SpooledTemporaryFile()
        self._tempfile_result_png = tempfile.SpooledTemporaryFile()

        if isinstance(sticker, Sticker):
            logger.debug('StickerFile object is a Sticker')
            self._is_sticker = True
            self._emoji = sticker.emoji if sticker.emoji is not None else '💈'
        elif isinstance(sticker, Document):
            logger.debug('StickerFile object is a Document')
            self._is_sticker = False
            if caption:
                self._emoji = utils.get_emojis(caption)
            if not self._emoji:
                self._emoji = '💈'

    @property
    def png_path(self):
        return self._png_path

    @property
    def emoji(self):
        return self._emoji

    @property
    def png_bytes_object(self):
        return self.get_png_bytes_object()

    @property
    def size(self):
        if self._size_resized == (0, 0):
            return self._size_original
        else:
            return self._size_resized

    @staticmethod
    def _raise_exception(received_error_message):
        for expected_api_error_message, exception_to_raise in EXCEPTIONS.items():
            if re.search(expected_api_error_message, received_error_message, re.I):
                raise exception_to_raise(received_error_message)

        # raise unknown error if no description matched
        raise EXCEPTIONS[''](received_error_message)

    def download(self, prepare_png=False, subdir=''):
        logger.debug('downloading sticker')
        new_file = self._file.get_file()

        if self._is_sticker:
            self._downloaded_file_path = 'tmp/{}downloaded_{}.webp'.format(subdir, self._file.file_id)
        else:  # if we are already working with a png document
            self._downloaded_file_path = 'tmp/{}downloaded_{}.png'.format(subdir, self._file.file_id)

        logger.debug('download path: %s', self._downloaded_file_path)
        new_file.download(self._downloaded_file_path)

        if prepare_png:
            return self.prepare_png(subdir=subdir)

    def prepare_png(self, subdir=''):
        logger.info('preparing png (source file: %s)', self._downloaded_file_path)

        im = Image.open(self._downloaded_file_path)

        logger.debug('original image size: %s', im.size)
        self._size_original = im.size
        if (im.size[0] > 512 or im.size[1] > 512) or (im.size[0] != 512 and im.size[1] != 512):
            logger.debug('resizing file because one of the sides is > 512px or at least one side is not 512px')
            correct_size = get_correct_size(im.size)
            self._size_resized = correct_size
            im = im.resize(correct_size, Image.ANTIALIAS)
        else:
            logger.debug('original size is ok')

        self._png_path = 'tmp/{}converted_{}.png'.format(subdir, self._file.file_id)

        logger.debug('saving PIL image object as png (%s)', self._png_path)
        im.save(self._png_path, 'png')
        im.close()

        return self._png_path

    def close(self, keep_result_png_open=False):
        # noinspection PyBroadException
        try:
            self._tempfile_downloaded.close()
        except Exception as e:
            logger.error('error while trying to close downloaded tempfile: %s', str(e))

        if not keep_result_png_open:
            # noinspection PyBroadException
            try:
                self._tempfile_result_png.close()
            except Exception as e:
                logger.error('error while trying to close result png tempfile: %s', str(e))

    def add_to_set(self, bot, user_id, pack_name):
        logger.debug('adding sticker to set %s', pack_name)

        try:
            bot.add_sticker_to_set(
                user_id=user_id,
                name=pack_name,
                emojis=self._emoji,
                png_sticker=self.png_bytes_object,
                mask_position=None
            )
            return 0
        except (BadRequest, TelegramError) as e:
            logger.error('Telegram exception while trying to add a sticker to %s: %s', pack_name, e.message)
            self._raise_exception(e.message)

    def remove_from_set(self, bot):
        logger.debug('removing sticker from set %s', self._file.set_name)

        try:
            bot.delete_sticker_from_set(self._file.file_id)
            return 0
        except (BadRequest, TelegramError) as e:
            logger.error('Telegram exception while trying to remove a sticker from %s: %s', self._file.set_name,
                         e.message)
            self._raise_exception(e.message)

    @classmethod
    def create_set(cls, bot, *args, **kwargs):
        try:
            return bot.create_new_sticker_set(*args, **kwargs)
        except (BadRequest, TelegramError) as e:
            logger.error('Telegram exception while trying to create a pack: %s', e.message)
            cls._raise_exception(e.message)

    def __repr__(self):
        return 'StickerFile object of original type {} (original size: {}, resized: {})'.format(
            'Sticker' if self._is_sticker else 'Document',
            self._size_original,
            self._size_resized
        )
