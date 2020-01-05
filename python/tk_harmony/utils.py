import os
import shutil
import fnmatch


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


def normpath(path):
    return os.path.abspath(os.path.realpath(path)).replace("\\", "/")


class Cached(object):
    def __init__(self, f, ttl=0, size_limit=0):
        self.func = f
        self.cache = {}
        self.size_limit = size_limit
        self.ttl = ttl
        self.ttls = {}

    def __call__(self, *args, **kwargs):
        import time

        key = str(args) + str(kwargs.items())
        if self.size_limit > 0 and len(self.cache) > self.size_limit:
            self.cache = {}

        cache_return = True
        if key in self.cache:
            if self.ttl > 0 and (time.time() - self.ttls[key] > self.ttl):
                del self.ttls[key]
                del self.cache[key]
            else:
                cache_return = False

        if cache_return:
            ret = self.func(*args, **kwargs)
            self.cache[key] = ret
            if self.ttl > 0:
                self.ttls[key] = time.time()
        else:
            ret = self.cache[key]

        return ret

    def __get__(self, instance, owner):
        from functools import partial

        return partial(self.__call__, instance)


def copy_tree(
    source_dir,
    target_dir,
    exclude_files=None,
    include_files=None,
    rename_files=None,
    copy_function=shutil.copy2,
    progress_callback=None,
):
    """
    Copies the files from the source folder ignoring the ones specified in
    the fexclude filters or including the ones specified in the include filters.
    Filters can be either a file name, or a fnmatch type pattern.

    Also rename files as it copies them if a rename_files mapping is chosen.
    Preserves permissions and resolves symlinks.
    """

    # collect the files to copy
    copy_files = set()
    make_directories = set()

    for root, dirs, files in os.walk(source_dir):
        relative_dir = os.path.relpath(root, source_dir)
        destination_dir = os.path.join(target_dir, relative_dir)
        make_directories.add(destination_dir)

        for file_ in files:
            source_file = os.path.join(root, file_)
            copy_file = True

            # check if we should exclude it
            if exclude_files:
                copy_file = file_ not in exclude_files
                for pattern in exclude_files:
                    if fnmatch.fnmatch(file_.lower(), pattern):
                        copy_file = False
                        break

            # but if we force the inclusion we make sure we add it back
            if include_files:
                for pattern in include_files:
                    if fnmatch.fnmatch(file_.lower(), pattern):
                        copy_file = True
                        break

            if copy_file:
                # check if we need to rename it
                if rename_files and file_ in rename_files:
                    file_ = rename_files[file_]

                # finally mark the file for copy
                destination_file = os.path.join(destination_dir, file_)
                copy_files.add((source_file, destination_file))

    copy_files_count = len(copy_files)

    # keep track of the files that were copied
    copied_files = []

    # create directories first
    for i, dir_ in enumerate(make_directories):
        if not os.path.exists(dir_):
            os.makedirs(dir_)

    # copy files after
    for i, (source_file, destination_file) in enumerate(copy_files):
        if progress_callback is not None:
            progress_info = {"source": source_file, "target": destination_file}

            progress_callback(i, copy_files_count, info=progress_info)

        # finally copy the file
        copy_function(source_file, destination_file)
        copied_files.append(destination_file)

    if progress_callback is not None:
        progress_callback(len(copied_files), copy_files_count)

    return copied_files
