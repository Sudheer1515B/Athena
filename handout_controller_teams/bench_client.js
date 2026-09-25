// Minimal WDR bench client for your server (Node.js, no packages needed).
//   node bench_client.js 127.0.0.1        (against: python wdr_tool.py serve-sim)
//   node bench_client.js <bench ip>       (against the real bench)
const net = require("net");

class Bench {
  constructor(host, port = 3333) {
    this.sock = net.connect(port, host);
    this.waiting = [];                    // resolvers for replies, in order
    this.chain = Promise.resolve();       // one command in flight at a time
    let buf = "";
    this.sock.on("data", (chunk) => {
      buf += chunk.toString("ascii");
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        // Every line from the bench is routed by its FIRST WORD.
        if (line.startsWith("OK") || line.startsWith("ERR")) {
          const resolve = this.waiting.shift();
          if (resolve) resolve(line);
        } else if (line.startsWith("TEL")) this.onTel(line);
        else if (line.startsWith("EVT")) this.onEvt(line);
      }
    });
  }

  // Send one command and wait for its one reply.
  cmd(line) {
    const p = this.chain.then(() => new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("no reply to " + line)), 2000);
      this.waiting.push((reply) => { clearTimeout(timer); resolve(reply); });
      this.sock.write(line + "\n");
    }));
    this.chain = p.catch(() => {});
    return p;
  }

  // Override these in your server: push to the browser, log to your database...
  onTel(line) { console.log("  telemetry:", line); }
  onEvt(line) { console.log("  event:    ", line); }
}

const kv = (reply) => Object.fromEntries(
  reply.split(" ").slice(2).filter((t) => t.includes("=")).map((t) => t.split("=")));

(async () => {
  const b = new Bench(process.argv[2] || "127.0.0.1");
  console.log(await b.cmd("INFO"));
  console.log(await b.cmd("STOP"));

  const frames = [[1500, 1500, 1500, 1500], [1600, 1400, 1500, 1700], [1700, 1300, 1500, 1900]];
  console.log(await b.cmd(`LOAD 10 ${frames.length}`));
  for (let i = 0; i < frames.length; i++) await b.cmd(`F ${i} ${frames[i].join(" ")}`);
  const reply = await b.cmd("COMMIT");
  const expected = frames.flat().reduce((a, v) => a + v, 0) % 65536;
  if (Number(reply.split("SUM=")[1]) !== expected) throw new Error("upload corrupted");
  console.log(reply);

  console.log(await b.cmd("TEL 1"));
  console.log(await b.cmd("START 5"));
  await new Promise((r) => setTimeout(r, 500));
  const s = kv(await b.cmd("STATUS"));
  console.log(`dashboard: state=${s.state} cycle ${s.cycle} of ${s.target}, ` +
              `${Math.floor(100 * s.frame / s.frames)}% through this cycle`);
  console.log(await b.cmd("STOP"));
  console.log(await b.cmd("COUNTERS"));
  b.sock.end();
})();
