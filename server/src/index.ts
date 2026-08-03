import express from "express";
import cors from "cors";
import dotenv from "dotenv";

dotenv.config();

const app = express();

app.use(cors());
app.use(express.json());

app.get("/", (req, res) => {
  res.json({
    status: "AI Factory Running 🚀",
    version: "0.1",
  });
});

const PORT = 4000;

app.listen(PORT, () => {
  console.log(`AI Factory running on http://localhost:${PORT}`);
});