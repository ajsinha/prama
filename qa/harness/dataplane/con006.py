import asyncio, sqlite3, tempfile, os
from prama.connect.spi import ConnectorError

async def main():
    obs = []
    tmpdir = tempfile.mkdtemp()
    dbpath = os.path.join(tmpdir, "t.db")
    conn = sqlite3.connect(dbpath)
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    csvpath = os.path.join(tmpdir, "d.csv")
    with open(csvpath, "w") as f:
        f.write("a,b\n1,2\n")

    from prama.connect.sources.sqlite import SqliteConnector
    from prama.connect.sources.filesystem import FilesystemConnector
    from prama.connect.sources.rest import RestConnector
    from prama.connect.sources.mongo import MongoConnector
    from prama.connect.sources.objectstore import ObjectStoreConnector

    async def probe(name, c, path):
        for method in ("describe", "snapshot"):
            try:
                await getattr(c, method)(path)
                obs.append(f"{name}.{method}: NO ERROR (succeeded)")
            except ConnectorError as e:
                obs.append(f"{name}.{method}: {getattr(e,'code',None)}")
            except Exception as e:
                obs.append(f"{name}.{method}: {type(e).__name__}: {e}")
        try:
            gen = c.read(path)
            await gen.__anext__()
            obs.append(f"{name}.read: NO ERROR (yielded a batch)")
        except ConnectorError as e:
            obs.append(f"{name}.read: {getattr(e,'code',None)}")
        except StopAsyncIteration:
            obs.append(f"{name}.read: StopAsyncIteration (no rows, no error)")
        except Exception as e:
            obs.append(f"{name}.read: {type(e).__name__}: {e}")

    await probe("sqlite", SqliteConnector({"database_path": dbpath}), ("t",))
    await probe("filesystem", FilesystemConnector({"root_path": tmpdir}), ("d.csv",))
    await probe("rest", RestConnector({"base_url": "http://localhost:1", "endpoints": ["x"]}), ("x",))
    await probe("mongodb", MongoConnector({"uri": "mongodb://localhost:1", "database": "d"}), ("coll",))
    await probe("objectstore", ObjectStoreConnector({"scheme": "s3", "bucket": "b", "prefix": "p", "endpoint": "localhost:1"}), ("p",))

    for line in obs:
        print(line)

asyncio.run(main())
